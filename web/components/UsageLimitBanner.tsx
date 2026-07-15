"use client";

// Shown at the top of Inbox + Dashboard once the workspace has hit its
// 500-email monthly cap. Backed by the shared `useWorkspace()` hook so both
// pages read the same fetch shape as the settings billing section.

import { AlertTriangle } from "lucide-react";
import { isOverUsageLimit, useWorkspace } from "@/lib/useWorkspace";

export default function UsageLimitBanner() {
  const { data } = useWorkspace();

  if (!isOverUsageLimit(data)) return null;

  return (
    <div className="flex items-start gap-2 rounded-[var(--radius-md)] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
      <AlertTriangle size={16} className="mt-0.5 shrink-0" />
      <span>
        You&apos;ve hit this month&apos;s 500-email limit — new emails are landing
        unprocessed.
      </span>
    </div>
  );
}
