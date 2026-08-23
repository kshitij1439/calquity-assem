"use client";

import { useEffect, useState, useCallback } from "react";
import { AccountSwitcher } from "@/components/account-switcher";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";
import dynamic from "next/dynamic";

const MascotViewport = dynamic(() => import("../components/MascotViewport"), {
  ssr: false,
});

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

interface SLABreach {
  ticket_id: string;
  account_id: string;
  account_name: string;
  severity: string;
  status: string;
  elapsed_minutes: number;
  target_minutes: number;
  breach_reason: string;
  urgency_score: number;
}

interface IssueCluster {
  known_issue_ref: string;
  ticket_count: number;
  account_count: number;
  llm_summary?: string;
}

interface Spike {
  issue_type: string;
  ticket_count: number;
  account_count: number;
}

interface DashboardData {
  sla_breaches: SLABreach[];
  issue_clusters: IssueCluster[];
  cross_customer_spikes: Spike[];
  snapshot_time: string;
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [account, setAccount] = useState({ id: "ACCT-001", name: "Northstar Logistics", role: "staff" });

  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/dashboard`, {
        headers: { "X-Account-ID": account.id, "X-User-Role": account.role },
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Failed to load dashboard");
      setData(await res.json());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [account]);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  const severityBadge = (s: string) => {
    if (s === "P1") return <Badge variant="destructive">P1</Badge>;
    if (s === "P2") return <Badge className="bg-orange-600 hover:bg-orange-500">P2</Badge>;
    return <Badge variant="secondary">P3</Badge>;
  };

  const urgencyColor = (score: number) => {
    if (score >= 3) return "text-red-400";
    if (score >= 2) return "text-orange-400";
    return "text-yellow-400";
  };

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur px-6 py-3 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
            <div className="w-8 h-8 rounded-lg overflow-hidden bg-indigo-950/60 border border-indigo-500/30 flex items-center justify-center">
              <MascotViewport />
            </div>
            <span className="text-white font-semibold text-sm">ParcelPilot</span>
          </Link>
          <span className="text-gray-600">/</span>
          <span className="text-gray-400 text-sm">Issue Dashboard</span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchDashboard}
            className="text-xs text-gray-400 hover:text-white px-3 py-1.5 rounded-lg border border-gray-700 hover:border-gray-500 transition-colors"
          >
            ↻ Refresh
          </button>
          <AccountSwitcher account={account} onChange={setAccount} />
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        {/* Snapshot notice */}
        <div className="text-xs text-gray-500 bg-gray-900/50 border border-gray-800 rounded-lg px-4 py-2 inline-block">
          📅 Data snapshot: 2026-08-16 11:00 IST — all SLA calculations reference this time
        </div>

        {loading && (
          <div className="text-center py-20 text-gray-400">
            <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            Loading dashboard...
          </div>
        )}

        {error && (
          <div className="bg-red-950/50 border border-red-800 rounded-xl px-6 py-4 text-red-400">
            {account.role !== "staff"
              ? "⚠ Dashboard access requires staff role. Switch to a staff account."
              : `Error: ${error}`}
          </div>
        )}

        {data && !loading && (
          <>
            {/* Summary cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card className="bg-gray-900 border-gray-800">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-400 font-medium">SLA Breaches</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-3xl font-bold text-red-400">{data.sla_breaches.length}</p>
                  <p className="text-xs text-gray-500 mt-1">Open tickets past target</p>
                </CardContent>
              </Card>
              <Card className="bg-gray-900 border-gray-800">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-400 font-medium">Known Issue Clusters</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-3xl font-bold text-yellow-400">{data.issue_clusters.length}</p>
                  <p className="text-xs text-gray-500 mt-1">Active KI groupings</p>
                </CardContent>
              </Card>
              <Card className="bg-gray-900 border-gray-800">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-400 font-medium">Cross-Customer Spikes</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-3xl font-bold text-purple-400">{data.cross_customer_spikes.length}</p>
                  <p className="text-xs text-gray-500 mt-1">Multi-account patterns (24h)</p>
                </CardContent>
              </Card>
            </div>

            {/* SLA Breaches */}
            <Card className="bg-gray-900 border-gray-800">
              <CardHeader>
                <CardTitle className="text-white flex items-center gap-2">
                  <span className="text-red-400">🔴</span> SLA Breaches
                  <Badge variant="destructive" className="ml-auto">{data.sla_breaches.length}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {data.sla_breaches.length === 0 ? (
                  <p className="text-gray-500 text-sm">No SLA breaches detected. ✓</p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow className="border-gray-800">
                        <TableHead className="text-gray-400">Ticket</TableHead>
                        <TableHead className="text-gray-400">Account</TableHead>
                        <TableHead className="text-gray-400">Severity</TableHead>
                        <TableHead className="text-gray-400">Elapsed</TableHead>
                        <TableHead className="text-gray-400">Target</TableHead>
                        <TableHead className="text-gray-400">Urgency</TableHead>
                        <TableHead className="text-gray-400">Reason</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.sla_breaches.map((b) => (
                        <TableRow key={b.ticket_id} className="border-gray-800 hover:bg-gray-800/50">
                          <TableCell className="text-white font-mono text-xs">{b.ticket_id}</TableCell>
                          <TableCell className="text-gray-300 text-xs">{b.account_name}</TableCell>
                          <TableCell>{severityBadge(b.severity)}</TableCell>
                          <TableCell className="text-gray-300 text-xs">{b.elapsed_minutes}m</TableCell>
                          <TableCell className="text-gray-500 text-xs">{b.target_minutes}m</TableCell>
                          <TableCell>
                            <span className={`text-xs font-bold ${urgencyColor(b.urgency_score)}`}>
                              {b.urgency_score}×
                            </span>
                          </TableCell>
                          <TableCell className="text-gray-400 text-xs max-w-xs truncate">{b.breach_reason}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>

            {/* Known Issue Clusters */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card className="bg-gray-900 border-gray-800">
                <CardHeader>
                  <CardTitle className="text-white flex items-center gap-2">
                    <span className="text-yellow-400">⚠</span> Known Issue Clusters
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {data.issue_clusters.length === 0 ? (
                    <p className="text-gray-500 text-sm">No active clusters.</p>
                  ) : (
                    data.issue_clusters.map((c) => (
                      <div key={c.known_issue_ref} className="flex items-start justify-between border border-gray-800 rounded-lg p-3">
                        <div>
                          <p className="text-yellow-400 font-mono text-sm font-bold">{c.known_issue_ref}</p>
                          {c.llm_summary && <p className="text-gray-400 text-xs mt-1">{c.llm_summary}</p>}
                        </div>
                        <div className="text-right">
                          <p className="text-white text-sm font-bold">{c.ticket_count}</p>
                          <p className="text-gray-500 text-xs">{c.account_count} accounts</p>
                        </div>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>

              {/* Cross-customer spikes */}
              <Card className="bg-gray-900 border-gray-800">
                <CardHeader>
                  <CardTitle className="text-white flex items-center gap-2">
                    <span className="text-purple-400">📈</span> Cross-Customer Spikes (24h)
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {data.cross_customer_spikes.length === 0 ? (
                    <p className="text-gray-500 text-sm">No cross-customer spikes detected.</p>
                  ) : (
                    data.cross_customer_spikes.map((s) => (
                      <div key={s.issue_type} className="flex items-center justify-between border border-gray-800 rounded-lg p-3">
                        <p className="text-gray-300 text-sm">{s.issue_type}</p>
                        <div className="text-right">
                          <p className="text-purple-400 font-bold text-sm">{s.account_count} accounts</p>
                          <p className="text-gray-500 text-xs">{s.ticket_count} tickets</p>
                        </div>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
