"use client";

import { useState } from "react";
import { X } from "lucide-react";

export default function PasteTextModal({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (title: string, text: string) => Promise<void> | void;
}) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = title.trim() !== "" && text.trim() !== "" && !submitting;

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(title.trim(), text);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4">
      <div className="w-full max-w-lg rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)] shadow-sm">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] px-5 py-4">
          <h2 className="text-sm font-semibold text-[var(--color-foreground)]">
            Paste text
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-muted)] hover:bg-[var(--color-app-bg)]"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex flex-col gap-3 px-5 py-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--color-muted)]">
              Title
            </label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Refund policy"
              className="w-full rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-app-bg)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--color-muted)]">
              Content
            </label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={8}
              placeholder="Paste the knowledge base content here..."
              className="w-full resize-none rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-app-bg)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
            />
          </div>
          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 border-t border-[var(--color-border)] px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-[var(--radius-sm)] px-3 py-1.5 text-sm text-[var(--color-muted)] hover:bg-[var(--color-app-bg)]"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {submitting ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
