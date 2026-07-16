"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiPost } from "@/lib/api";
import ConfidenceBadge from "@/components/ConfidenceBadge";
import CategoryPill from "@/components/CategoryPill";
import Spinner from "@/components/Spinner";

export type AttentionRow = {
  id: string;
  customerEmail: string | null;
  subject: string;
  category: string | null;
  confidence: number | null;
  waitingSinceIso: string | null;
};

function formatRelativeAge(value: string | null): string {
  if (!value) return "";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "";
  const diffMin = Math.round((Date.now() - then) / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d`;
}

export default function AttentionList({
  rows,
  onRowRemoved,
  onApproveFailed,
}: {
  rows: AttentionRow[];
  onRowRemoved: (id: string) => void;
  onApproveFailed?: () => void;
}) {
  const router = useRouter();
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleApprove(id: string) {
    setError(null);
    setApprovingId(id);
    onRowRemoved(id);
    try {
      await apiPost(`threads/${id}/approve`, {});
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to approve");
      onApproveFailed?.();
    } finally {
      setApprovingId(null);
    }
  }

  if (rows.length === 0) {
    return (
      <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white px-6 py-14 text-center shadow-[var(--shadow-card)]">
        <p className="text-[15px] font-medium text-[var(--color-foreground)]">
          All clear
        </p>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          Nothing needs your attention right now.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* Phones/tablets: stacked rows with a full-width approve action. */}
      <ul className="divide-y divide-[var(--color-border)] rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] lg:hidden">
        {rows.map((row) => (
          <li
            key={row.id}
            onClick={() => router.push(`/inbox/${row.id}`)}
            className="flex cursor-pointer flex-col gap-2.5 px-4 py-4 transition-colors hover:bg-[var(--color-app-bg)]"
          >
            <div className="flex items-baseline justify-between gap-3">
              <span className="min-w-0 truncate text-sm font-medium text-[var(--color-foreground)]">
                {row.subject}
              </span>
              <span className="readout shrink-0 text-xs text-[var(--color-muted)]">
                {formatRelativeAge(row.waitingSinceIso)}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="min-w-0 truncate text-[13px] text-[var(--color-muted)]">
                {row.customerEmail || "Unknown"}
              </span>
              <CategoryPill category={row.category} />
              <ConfidenceBadge confidence={row.confidence} />
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                void handleApprove(row.id);
              }}
              disabled={approvingId === row.id}
              className="mt-1 inline-flex w-full items-center justify-center gap-1.5 rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-3.5 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
            >
              {approvingId === row.id && <Spinner size={13} />}
              {approvingId === row.id ? "Sending..." : "Approve"}
            </button>
          </li>
        ))}
      </ul>

      <div className="hidden overflow-x-auto rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] lg:block">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border)] bg-[var(--color-app-bg)]/60 text-xs uppercase tracking-wide text-[var(--color-muted)]">
              <th className="px-5 py-3 font-medium">Customer</th>
              <th className="px-5 py-3 font-medium">Subject</th>
              <th className="px-5 py-3 font-medium">Category</th>
              <th className="px-5 py-3 font-medium">Confidence</th>
              <th className="px-5 py-3 font-medium">Waiting</th>
              <th className="px-5 py-3 font-medium" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                onClick={() => router.push(`/inbox/${row.id}`)}
                className="cursor-pointer border-b border-[var(--color-border)] transition-colors last:border-0 hover:bg-[var(--color-app-bg)]"
              >
                <td className="px-5 py-3.5 text-[var(--color-muted)]">
                  {row.customerEmail || "Unknown"}
                </td>
                <td className="max-w-xs truncate px-5 py-3.5 font-medium text-[var(--color-foreground)]">
                  {row.subject}
                </td>
                <td className="px-5 py-3.5">
                  <CategoryPill category={row.category} />
                </td>
                <td className="px-5 py-3.5">
                  <ConfidenceBadge confidence={row.confidence} />
                </td>
                <td className="readout px-5 py-3.5 text-xs text-[var(--color-muted)]">
                  {formatRelativeAge(row.waitingSinceIso)}
                </td>
                <td className="px-5 py-3.5 text-right">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleApprove(row.id);
                    }}
                    disabled={approvingId === row.id}
                    className="inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-3.5 py-2 text-xs font-medium text-white shadow-sm transition-colors hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
                  >
                    {approvingId === row.id && <Spinner size={12} />}
                    {approvingId === row.id ? "Sending..." : "Approve"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
