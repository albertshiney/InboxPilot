"use client"; // Error boundaries must be Client Components

// Route-level error boundary for everything under the (app) group
// (dashboard/inbox/knowledge/settings). Catches render-time exceptions that
// escape a page's own try/catch (e.g. a bad response shape crashing a
// render) so the user gets a recoverable screen instead of a blank one.

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-50 text-red-600">
        <AlertTriangle size={18} />
      </div>
      <h2 className="text-base font-semibold text-[var(--color-foreground)]">
        Something went wrong
      </h2>
      <p className="max-w-sm text-sm text-[var(--color-muted)]">
        An unexpected error occurred loading this page. You can try again, or
        head back to the dashboard.
      </p>
      <div className="mt-1 flex items-center gap-2">
        <button
          type="button"
          onClick={() => reset()}
          className="rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-3 py-1.5 text-sm font-medium text-white"
        >
          Try again
        </button>
        <a
          href="/dashboard"
          className="rounded-[var(--radius-sm)] border border-[var(--color-border)] px-3 py-1.5 text-sm font-medium text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
        >
          Back to dashboard
        </a>
      </div>
    </div>
  );
}
