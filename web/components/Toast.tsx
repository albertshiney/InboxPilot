"use client";

// Minimal floating toast for failed mutations — no toast library, just a
// fixed-position notification that self-dismisses. Pages/components keep
// their own inline error text for in-context detail; this adds a
// hard-to-miss signal for actions that happen off-screen from where the
// user is looking (e.g. a save button at the top of a long settings page).

import { useEffect } from "react";
import { AlertCircle } from "lucide-react";

const AUTO_DISMISS_MS = 4000;

export default function Toast({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss: () => void;
}) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [message, onDismiss]);

  return (
    <div
      role="alert"
      className="fixed bottom-4 right-4 z-50 flex max-w-sm items-start gap-2 rounded-[var(--radius-sm)] border border-red-200 bg-white px-4 py-3 text-sm text-red-700 shadow-lg"
    >
      <AlertCircle size={15} className="mt-0.5 shrink-0" />
      <span className="flex-1">{message}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="shrink-0 text-red-400 hover:text-red-600"
      >
        ×
      </button>
    </div>
  );
}
