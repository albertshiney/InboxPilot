"use client";

// Save button + inline "Saved" confirmation / error, shared by every
// settings section that PATCHes /settings. Failed saves additionally raise
// a floating Toast — the inline error text is easy to miss on a long
// settings page if the section that failed isn't currently in view.

import { useState } from "react";
import Spinner from "@/components/Spinner";
import Toast from "@/components/Toast";

export default function SaveBar({
  onSave,
  saving,
  saved,
  error,
  label = "Save",
}: {
  onSave: () => void;
  saving: boolean;
  saved: boolean;
  error: string | null;
  label?: string;
}) {
  const [toastDismissed, setToastDismissed] = useState(false);

  // A fresh error (including the exact same message from a retried save)
  // should re-show the toast rather than staying dismissed forever —
  // adjusted during render (React's guidance for resetting state in
  // response to a prop change) rather than in an Effect, same pattern
  // DraftPanel uses for `seenDraftId`.
  const [seenError, setSeenError] = useState(error);
  if (error !== seenError) {
    setSeenError(error);
    setToastDismissed(false);
  }

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={onSave}
        disabled={saving}
        className="inline-flex w-fit items-center gap-2 rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {saving && <Spinner size={14} />}
        {saving ? "Saving..." : label}
      </button>
      {saved && <span className="text-sm text-emerald-600">Saved</span>}
      {error && <span className="text-sm text-red-600">{error}</span>}
      {error && !toastDismissed && (
        <Toast message={error} onDismiss={() => setToastDismissed(true)} />
      )}
    </div>
  );
}
