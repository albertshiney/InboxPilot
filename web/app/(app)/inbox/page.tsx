"use client";

// Inbox list: tabs map to the /threads status filter, keyboard nav
// (up/down select, Enter open, A approve on the needs-review tab), and a
// per-tab empty state.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet, apiPost } from "@/lib/api";
import ConfidenceBadge from "@/components/ConfidenceBadge";
import CategoryPill from "@/components/CategoryPill";
import UsageLimitBanner from "@/components/UsageLimitBanner";

type Tab = "needs_review" | "auto_sent" | "sent" | "all";

const TABS: { key: Tab; label: string; status?: string }[] = [
  { key: "needs_review", label: "Needs review", status: "needs_review" },
  { key: "auto_sent", label: "Auto-sent", status: "auto_sent" },
  { key: "sent", label: "Sent", status: "sent" },
  { key: "all", label: "All" },
];

const EMPTY_STATE: Record<Tab, string> = {
  needs_review: "Inbox zero 🎉",
  auto_sent: "No auto-sent replies yet.",
  sent: "No sent replies yet.",
  all: "No threads yet.",
};

type ThreadRow = {
  id: string;
  subject: string;
  snippet: string;
  customerName: string | null;
  customerEmail: string | null;
  status: string;
  lastMessageAt: string;
  confidence: number | null;
  category: string | null;
};

function formatRelativeAge(value: string): string {
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "";
  const diffMin = Math.round((Date.now() - then) / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d ago`;
}

export default function InboxPage() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("needs_review");
  const [items, setItems] = useState<ThreadRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState(0);

  const status = useMemo(() => TABS.find((t) => t.key === tab)?.status, [tab]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const path = status ? `threads?status=${status}` : "threads";
      const data = await apiGet<{ items: ThreadRow[]; total: number; page: number }>(path);
      setItems(data.items);
      setSelected(0);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load threads");
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    async function run() {
      await load();
    }
    void run();
  }, [load]);

  const handleApprove = useCallback(
    async (id: string) => {
      setItems((prev) => prev.filter((row) => row.id !== id));
      try {
        await apiPost(`threads/${id}/approve`, {});
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to approve");
        void load();
      }
    },
    [load],
  );

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (items.length === 0) return;
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelected((s) => Math.min(items.length - 1, s + 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelected((s) => Math.max(0, s - 1));
      } else if (e.key === "Enter") {
        const row = items[selected];
        if (row) router.push(`/inbox/${row.id}`);
      } else if ((e.key === "a" || e.key === "A") && tab === "needs_review") {
        const row = items[selected];
        if (row) void handleApprove(row.id);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [items, selected, tab, router, handleApprove]);

  return (
    <div className="flex flex-col gap-4">
      <UsageLimitBanner />
      <h1 className="text-xl font-semibold text-[var(--color-foreground)]">Inbox</h1>

      <div className="flex gap-1 border-b border-[var(--color-border)]">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`px-3 py-2 text-sm font-medium ${
              tab === t.key
                ? "border-b-2 border-[var(--color-accent)] text-[var(--color-accent)]"
                : "text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="overflow-hidden rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)] shadow-sm">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border)] text-xs text-[var(--color-muted)]">
              <th className="px-4 py-2.5 font-medium">Customer</th>
              <th className="px-4 py-2.5 font-medium">Subject</th>
              <th className="px-4 py-2.5 font-medium">Category</th>
              <th className="px-4 py-2.5 font-medium">Confidence</th>
              <th className="px-4 py-2.5 font-medium">Age</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-[var(--color-muted)]">
                  Loading...
                </td>
              </tr>
            )}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-[var(--color-muted)]">
                  {EMPTY_STATE[tab]}
                </td>
              </tr>
            )}
            {!loading &&
              items.map((row, i) => (
                <tr
                  key={row.id}
                  onClick={() => router.push(`/inbox/${row.id}`)}
                  onMouseEnter={() => setSelected(i)}
                  className={`cursor-pointer border-b border-[var(--color-border)] last:border-0 ${
                    i === selected ? "bg-[var(--color-accent-soft)]" : "hover:bg-[var(--color-app-bg)]"
                  }`}
                >
                  <td className="px-4 py-2.5">{row.customerName || row.customerEmail || "Unknown"}</td>
                  <td className="max-w-xs px-4 py-2.5">
                    <div className="truncate font-medium text-[var(--color-foreground)]">
                      {row.subject}
                    </div>
                    <div className="truncate text-xs text-[var(--color-muted)]">{row.snippet}</div>
                  </td>
                  <td className="px-4 py-2.5">
                    <CategoryPill category={row.category} />
                  </td>
                  <td className="px-4 py-2.5">
                    <ConfidenceBadge confidence={row.confidence} />
                  </td>
                  <td className="px-4 py-2.5 text-[var(--color-muted)]">
                    {formatRelativeAge(row.lastMessageAt)}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
