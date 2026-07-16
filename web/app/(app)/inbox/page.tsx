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
import Spinner from "@/components/Spinner";

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
    <div className="flex flex-col gap-5">
      <UsageLimitBanner />
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight text-[var(--color-foreground)] sm:text-3xl">
          Inbox
        </h1>
        <p className="mt-1 text-[15px] text-[var(--color-muted)]">
          Review drafts, approve with one click, or open a thread for detail.
        </p>
      </div>

      <div className="scrollbar-none flex gap-1 overflow-x-auto border-b border-[var(--color-border)]">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`whitespace-nowrap border-b-2 px-4 py-2.5 text-[15px] font-medium transition-colors ${
              tab === t.key
                ? "border-[var(--color-accent)] text-[var(--color-accent)]"
                : "border-transparent text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* Phones/tablets: stacked rows, no sideways scrolling. */}
      <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] lg:hidden">
        {loading && (
          <div className="px-4 py-8 text-center text-[var(--color-muted)]">
            <span className="inline-flex items-center gap-2.5 text-sm">
              <Spinner size={16} className="text-[var(--color-accent)]" />
              Loading threads
            </span>
          </div>
        )}
        {!loading && items.length === 0 && (
          <div className="px-4 py-14 text-center text-[15px] text-[var(--color-muted)]">
            {EMPTY_STATE[tab]}
          </div>
        )}
        {!loading && items.length > 0 && (
          <ul className="divide-y divide-[var(--color-border)]">
            {items.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  onClick={() => router.push(`/inbox/${row.id}`)}
                  className="flex w-full flex-col gap-2 px-4 py-4 text-left transition-colors hover:bg-[var(--color-app-bg)]"
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="min-w-0 truncate text-sm font-medium text-[var(--color-foreground)]">
                      {row.subject}
                    </span>
                    <span className="readout shrink-0 text-xs text-[var(--color-muted)]">
                      {formatRelativeAge(row.lastMessageAt)}
                    </span>
                  </div>
                  <p className="truncate text-[13px] text-[var(--color-muted)]">{row.snippet}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="min-w-0 truncate text-[13px] text-[var(--color-muted)]">
                      {row.customerName || row.customerEmail || "Unknown"}
                    </span>
                    <CategoryPill category={row.category} />
                    <ConfidenceBadge confidence={row.confidence} />
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="hidden overflow-x-auto rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] lg:block">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border)] bg-[var(--color-app-bg)]/60 text-xs uppercase tracking-wide text-[var(--color-muted)]">
              <th className="px-5 py-3 font-medium">Customer</th>
              <th className="px-5 py-3 font-medium">Subject</th>
              <th className="px-5 py-3 font-medium">Category</th>
              <th className="px-5 py-3 font-medium">Confidence</th>
              <th className="px-5 py-3 font-medium">Age</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="px-5 py-8 text-center text-[var(--color-muted)]">
                  <span className="inline-flex items-center gap-2.5 text-sm">
                    <Spinner size={16} className="text-[var(--color-accent)]" />
                    Loading threads
                  </span>
                </td>
              </tr>
            )}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-14 text-center text-[15px] text-[var(--color-muted)]">
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
                  className={`cursor-pointer border-b border-[var(--color-border)] transition-colors last:border-0 ${
                    i === selected ? "bg-[var(--color-accent-soft)]/70" : "hover:bg-[var(--color-app-bg)]"
                  }`}
                >
                  <td className="px-5 py-3.5 text-[var(--color-muted)]">
                    {row.customerName || row.customerEmail || "Unknown"}
                  </td>
                  <td className="max-w-xs px-5 py-3.5">
                    <div className="truncate font-medium text-[var(--color-foreground)]">
                      {row.subject}
                    </div>
                    <div className="mt-0.5 truncate text-[13px] text-[var(--color-muted)]">
                      {row.snippet}
                    </div>
                  </td>
                  <td className="px-5 py-3.5">
                    <CategoryPill category={row.category} />
                  </td>
                  <td className="px-5 py-3.5">
                    <ConfidenceBadge confidence={row.confidence} />
                  </td>
                  <td className="readout px-5 py-3.5 text-xs text-[var(--color-muted)]">
                    {formatRelativeAge(row.lastMessageAt)}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <p className="hidden text-[13px] text-[var(--color-faint)] lg:block">
        <kbd className="readout rounded border border-[var(--color-border)] bg-white px-1.5 py-0.5 text-[11px]">↑↓</kbd>{" "}
        navigate ·{" "}
        <kbd className="readout rounded border border-[var(--color-border)] bg-white px-1.5 py-0.5 text-[11px]">Enter</kbd>{" "}
        open ·{" "}
        <kbd className="readout rounded border border-[var(--color-border)] bg-white px-1.5 py-0.5 text-[11px]">A</kbd>{" "}
        approve
      </p>
    </div>
  );
}
