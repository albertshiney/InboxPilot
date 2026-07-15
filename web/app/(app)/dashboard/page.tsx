"use client";

// Dashboard: four period-scoped StatCards (today/7d/30d) plus the live
// needs-review attention list with inline one-click approve.

import { useCallback, useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import StatCard from "@/components/StatCard";
import AttentionList, { type AttentionRow } from "@/components/AttentionList";

type Period = "today" | "7d" | "30d";

const PERIODS: { key: Period; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "7d", label: "7 days" },
  { key: "30d", label: "30 days" },
];

type Stats = {
  needsReview: number;
  emailsReceived: number;
  draftsCreated: number;
  autoSent: number;
  autoSentPct: number;
  attention: AttentionRow[];
};

export default function DashboardPage() {
  const [period, setPeriod] = useState<Period>("today");
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (p: Period) => {
    setLoading(true);
    try {
      const data = await apiGet<Stats>(`dashboard/stats?period=${p}`);
      setStats(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load dashboard stats");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    async function run() {
      await load(period);
    }
    void run();
  }, [period, load]);

  function handleRowRemoved(id: string) {
    setStats((prev) =>
      prev
        ? {
            ...prev,
            needsReview: Math.max(0, prev.needsReview - 1),
            attention: prev.attention.filter((row) => row.id !== id),
          }
        : prev,
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--color-foreground)]">Dashboard</h1>
        <div className="flex gap-1 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-card-bg)] p-1">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              type="button"
              onClick={() => setPeriod(p.key)}
              className={`rounded-[var(--radius-sm)] px-3 py-1 text-sm font-medium transition-colors ${
                period === p.key
                  ? "bg-[var(--color-accent)] text-white"
                  : "text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Needs review"
          value={String(stats?.needsReview ?? 0)}
          href="/inbox"
          loading={loading && !stats}
        />
        <StatCard
          label="Emails received"
          value={String(stats?.emailsReceived ?? 0)}
          loading={loading && !stats}
        />
        <StatCard
          label="Drafts created"
          value={String(stats?.draftsCreated ?? 0)}
          loading={loading && !stats}
        />
        <StatCard
          label="Auto-sent"
          value={`${stats?.autoSent ?? 0} (${stats?.autoSentPct ?? 0}%)`}
          loading={loading && !stats}
        />
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold text-[var(--color-foreground)]">
          Needs your attention
        </h2>
        <AttentionList
          rows={stats?.attention ?? []}
          onRowRemoved={handleRowRemoved}
          onApproveFailed={() => void load(period)}
        />
      </div>
    </div>
  );
}
