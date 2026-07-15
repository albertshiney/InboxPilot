"use client";

// Right pane of the thread view: meta strip (confidence/category/sources/
// reasoning), an editable reply textarea, and the approve/regenerate/
// discard actions. Renders a read-only state when the thread has no
// pending draft (already resolved, or discarded).

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import ConfidenceBadge from "@/components/ConfidenceBadge";
import CategoryPill from "@/components/CategoryPill";

export type Draft = {
  id: string;
  reply: string;
  confidence: number | null;
  category: string | null;
  reasoning: string;
  sourcesUsed: string[];
  status: string;
  editedReply: string | null;
};

export default function DraftPanel({
  draft,
  onApprove,
  onRegenerate,
  onDiscard,
}: {
  draft: Draft | null;
  onApprove: (body?: string) => Promise<void> | void;
  onRegenerate: (instruction?: string) => Promise<void> | void;
  onDiscard: () => Promise<void> | void;
}) {
  const [body, setBody] = useState(draft?.reply ?? "");
  const [instruction, setInstruction] = useState("");
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  const [approving, setApproving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset the editable body whenever a new draft (e.g. after Regenerate)
  // comes in — adjusted during render per React's guidance, rather than in
  // an Effect, so it can't lag a render behind.
  const [seenDraftId, setSeenDraftId] = useState(draft?.id);
  if (draft?.id !== seenDraftId) {
    setSeenDraftId(draft?.id);
    setBody(draft?.reply ?? "");
  }

  if (!draft) {
    return (
      <div className="flex items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)] p-6 text-sm text-[var(--color-muted)]">
        No draft for this thread.
      </div>
    );
  }

  const isPending = draft.status === "pending";
  const busy = approving || regenerating || discarding;

  const sourceCounts = draft.sourcesUsed.reduce<Record<string, number>>((acc, name) => {
    acc[name] = (acc[name] ?? 0) + 1;
    return acc;
  }, {});
  const sourceEntries = Object.entries(sourceCounts);

  async function handleApprove() {
    setError(null);
    setApproving(true);
    try {
      await onApprove(body !== draft?.reply ? body : undefined);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to approve");
    } finally {
      setApproving(false);
    }
  }

  async function handleRegenerate() {
    setError(null);
    setRegenerating(true);
    try {
      await onRegenerate(instruction.trim() || undefined);
      setInstruction("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to regenerate");
    } finally {
      setRegenerating(false);
    }
  }

  async function handleDiscard() {
    setError(null);
    setDiscarding(true);
    try {
      await onDiscard();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to discard");
    } finally {
      setDiscarding(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)] p-5">
      <div className="flex flex-wrap items-center gap-2">
        <ConfidenceBadge confidence={draft.confidence} />
        <CategoryPill category={draft.category} />
        {!isPending && (
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
            {draft.status}
          </span>
        )}
      </div>

      {sourceEntries.length > 0 && (
        <div className="text-xs text-[var(--color-muted)]">
          <button
            type="button"
            onClick={() => setSourcesExpanded((v) => !v)}
            className="flex items-center gap-1 hover:text-[var(--color-foreground)]"
          >
            {sourcesExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Sources:{" "}
            {sourceEntries
              .map(([name, count]) => `${name}${count > 1 ? ` ×${count}` : ""}`)
              .join(", ")}
          </button>
          {sourcesExpanded && (
            <ul className="mt-1.5 list-disc space-y-1 pl-5">
              {draft.sourcesUsed.map((name, i) => (
                <li key={`${name}-${i}`}>{name}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {draft.reasoning && (
        <p className="text-xs italic text-[var(--color-muted)]">{draft.reasoning}</p>
      )}

      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        readOnly={!isPending}
        rows={12}
        className="w-full resize-y rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-app-bg)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)] read-only:opacity-70"
      />

      {error && <p className="text-sm text-red-600">{error}</p>}

      {isPending && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleApprove}
              disabled={busy}
              className="rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
            >
              {approving ? "Sending..." : "Approve & send"}
            </button>
            <button
              type="button"
              onClick={handleDiscard}
              disabled={busy}
              className="rounded-[var(--radius-sm)] border border-[var(--color-border)] px-3 py-1.5 text-sm font-medium text-[var(--color-muted)] hover:text-red-600 disabled:opacity-60"
            >
              {discarding ? "Discarding..." : "Discard"}
            </button>
          </div>

          <div className="flex items-center gap-2">
            <input
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="Optional instruction, e.g. 'make it shorter'"
              className="flex-1 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-app-bg)] px-3 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
            />
            <button
              type="button"
              onClick={handleRegenerate}
              disabled={busy}
              className="shrink-0 rounded-[var(--radius-sm)] border border-[var(--color-border)] px-3 py-1.5 text-sm font-medium text-[var(--color-foreground)] hover:bg-[var(--color-app-bg)] disabled:opacity-60"
            >
              {regenerating ? "Regenerating..." : "Regenerate"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
