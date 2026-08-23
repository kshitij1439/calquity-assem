"""
app/config.py
─────────────
Central configuration loaded from environment variables via pydantic-settings.
The SNAPSHOT_NOW constant is fixed from the workbook README sheet and must
never be replaced with datetime.now().
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── Frozen reference time (from workbook README) ──────────────────────────────
# This is the dataset snapshot timestamp. All SLA and time-based calculations
# use this value — never datetime.now().
SNAPSHOT_NOW: datetime = datetime(
    2026, 8, 16, 11, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata")
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM ───────────────────────────────────────────────────────────────────
    groq_api_key: str = ""
    gemini_api_key: str = ""
    primary_model: str = "gemini-2.5-flash"
    fallback_model: str = "gemini-2.5-flash-lite"
    # After this many consecutive Groq failures, switch to fallback for session
    llm_circuit_breaker_threshold: int = 3
    llm_timeout_seconds: int = 30
    llm_max_retries: int = 2

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "calquity"
    qdrant_vector_size: int = 384  # sentence-transformers/all-MiniLM-L6-v2

    # ── Postgres ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://parcelpilot:parcelpilot@postgres:5432/parcelpilot"
    sync_database_url: str = "postgresql+psycopg2://parcelpilot:parcelpilot@postgres:5432/parcelpilot"

    # ── Action tokens ─────────────────────────────────────────────────────────
    action_token_secret: str = "insecure-dev-secret-change-in-production"
    action_token_ttl_seconds: int = 300  # 5 minutes

    # ── App ───────────────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"
    backend_cors_origins: list[str] | str = ["http://localhost:3000"]

    # ── Chunking ──────────────────────────────────────────────────────────────
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # ── Dashboard analytics ───────────────────────────────────────────────────
    spike_window_hours: int = 24
    spike_min_accounts: int = 2

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return v
        return ["http://localhost:3000"]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
