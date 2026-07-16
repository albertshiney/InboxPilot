"use client";

// Standalone AI behavior page — same `useWorkspace()` fetch pattern as the
// settings page, rendering the AI behavior and automation cards on their own
// route.

import { useWorkspace } from "@/lib/useWorkspace";
import AIBehaviorSection from "@/components/settings/AIBehaviorSection";
import AutomationSection from "@/components/settings/AutomationSection";
import { PageLoader } from "@/components/Spinner";

export default function AIBehaviorClient() {
  const { data, loading, error, refresh } = useWorkspace();

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight text-[var(--color-foreground)] sm:text-3xl">
          AI behavior
        </h1>
        <p className="mt-1 text-[15px] text-[var(--color-muted)]">
          Tune how InboxPilot writes and when it&apos;s allowed to send on its
          own.
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {loading && !data && <PageLoader label="Loading settings" />}

      {data && (
        <div className="flex flex-col gap-6">
          <AIBehaviorSection settings={data.settings} refresh={refresh} />
          <AutomationSection settings={data.settings} refresh={refresh} />
        </div>
      )}
    </div>
  );
}
