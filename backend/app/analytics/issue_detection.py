"""
app/analytics/issue_detection.py
──────────────────────────────────
Proactive issue detection for the dashboard.
Pure Postgres aggregation — no LLM required for detection.
Optional: one LLM call per cluster for a human-readable summary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog

from app.config import SNAPSHOT_NOW, get_settings
from app.data.database import get_db
from app.data.repository import (
    SLAStatus,
    check_sla,
    get_all_open_tickets_with_accounts,
    get_cross_customer_spikes,
    get_known_issue_clusters,
    resolve_sla_target_minutes,
)

settings = get_settings()
log = structlog.get_logger()


@dataclass
class SLABreachSummary:
    ticket_id: str
    account_id: str
    account_name: str
    severity: str
    status: str
    elapsed_minutes: float
    target_minutes: int
    breach_reason: str
    urgency_score: float  # higher = more urgent


@dataclass
class IssueCluster:
    known_issue_ref: str
    ticket_count: int
    account_count: int
    llm_summary: str | None = None


@dataclass
class CrossCustomerSpike:
    issue_type: str
    ticket_count: int
    account_count: int


def get_sla_breaches() -> list[SLABreachSummary]:
    """
    Return all open tickets where first-response SLA has been breached,
    sorted by urgency (elapsed / target ratio descending).
    Uses SNAPSHOT_NOW as the reference time — never datetime.now().
    """
    breaches: list[SLABreachSummary] = []

    with get_db() as db:
        rows = get_all_open_tickets_with_accounts(db)
        for ticket, account in rows:
            if ticket.created_at is None:
                continue

            target = resolve_sla_target_minutes(
                account.id, ticket.severity.value, account.plan.value
            )

            elapsed = (SNAPSHOT_NOW - ticket.created_at).total_seconds() / 60

            if ticket.first_response_at:
                elapsed = (ticket.first_response_at - ticket.created_at).total_seconds() / 60

            if elapsed > target:
                urgency = elapsed / max(target, 1)
                breaches.append(
                    SLABreachSummary(
                        ticket_id=ticket.id,
                        account_id=account.id,
                        account_name=account.name,
                        severity=ticket.severity.value,
                        status=ticket.status.value,
                        elapsed_minutes=round(elapsed, 1),
                        target_minutes=target,
                        breach_reason=(
                            f"Elapsed {elapsed:.0f} min vs {target} min target"
                        ),
                        urgency_score=round(urgency, 2),
                    )
                )

    breaches.sort(key=lambda x: x.urgency_score, reverse=True)
    log.info("analytics.sla_breaches", count=len(breaches))
    return breaches


def get_issue_clusters(include_llm_summary: bool = False) -> list[IssueCluster]:
    """
    Group tickets by known_issue_ref (KI-208, KI-211, etc.).
    Optionally generate a one-line LLM summary per cluster.
    The LLM call is isolated from the chat agent.
    """
    with get_db() as db:
        rows = get_known_issue_clusters(db)

    clusters = [
        IssueCluster(
            known_issue_ref=row["known_issue_ref"],
            ticket_count=row["ticket_count"],
            account_count=row["account_count"],
        )
        for row in rows
    ]

    if include_llm_summary:
        for cluster in clusters:
            cluster.llm_summary = _generate_cluster_summary(cluster)

    log.info("analytics.issue_clusters", count=len(clusters))
    return clusters


def get_spikes() -> list[CrossCustomerSpike]:
    """Detect same issue_type across >= N accounts in a rolling window."""
    with get_db() as db:
        rows = get_cross_customer_spikes(
            db,
            window_hours=settings.spike_window_hours,
            min_accounts=settings.spike_min_accounts,
        )
    spikes = [
        CrossCustomerSpike(
            issue_type=row["issue_type"],
            ticket_count=row["ticket_count"],
            account_count=row["account_count"],
        )
        for row in rows
    ]
    log.info("analytics.spikes", count=len(spikes))
    return spikes


def _generate_cluster_summary(cluster: IssueCluster) -> str:
    """
    Optional LLM call for a one-line cluster summary.
    Completely isolated from the chat agent — a hallucination here
    does not affect answer trustworthiness.
    """
    try:
        from langchain_groq import ChatGroq
        from langchain_core.messages import HumanMessage

        llm = ChatGroq(
            model=settings.primary_model,
            api_key=settings.groq_api_key,
            timeout=10,
        )
        response = llm.invoke([
            HumanMessage(content=(
                f"In one sentence, summarise the impact of known issue "
                f"{cluster.known_issue_ref} affecting {cluster.ticket_count} tickets "
                f"across {cluster.account_count} accounts."
            ))
        ])
        return response.content
    except Exception as e:
        log.warning("analytics.cluster_summary.failed", error=str(e))
        return f"{cluster.ticket_count} tickets, {cluster.account_count} accounts affected."
