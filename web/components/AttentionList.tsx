"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiPost } from "@/lib/api";
import ConfidenceBadge from "@/components/ConfidenceBadge";
import CategoryPill from "@/components/CategoryPill";

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
      <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)] px-4 py-10 text-center text-sm text-[var(--color-muted)] shadow-sm">
        Nothing needs your attention right now.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="overflow-hidden rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)] shadow-sm">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border)] text-xs text-[var(--color-muted)]">
              <th className="px-4 py-2.5 font-medium">Customer</th>
              <th className="px-4 py-2.5 font-medium">Subject</th>
              <th className="px-4 py-2.5 font-medium">Category</th>
              <th className="px-4 py-2.5 font-medium">Confidence</th>
              <th className="px-4 py-2.5 font-medium">Waiting</th>
              <th className="px-4 py-2.5 font-medium" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                onClick={() => router.push(`/inbox/${row.id}`)}
                className="cursor-pointer border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-app-bg)]"
              >
                <td className="px-4 py-2.5">{row.customerEmail || "Unknown"}</td>
                <td className="max-w-xs truncate px-4 py-2.5 font-medium text-[var(--color-foreground)]">
                  {row.subject}
                </td>
                <td className="px-4 py-2.5">
                  <CategoryPill category={row.category} />
                </td>
                <td className="px-4 py-2.5">
                  <ConfidenceBadge confidence={row.confidence} />
                </td>
                <td className="px-4 py-2.5 text-[var(--color-muted)]">
                  {formatRelativeAge(row.waitingSinceIso)}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleApprove(row.id);
                    }}
                    disabled={approvingId === row.id}
                    className="rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                  >
                    Approve
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
