"use client";

// Shown at the top of Inbox + Dashboard for two cases (task 15 adds the
// second): the workspace has never started (or has lost) its subscription —
// email processing requires an active/trialing subscription, so nothing is
// being drafted — or a subscribed workspace has hit its 500-email monthly
// cap. Backed by the shared `useWorkspace()` hook so both pages read the
// same fetch shape as the settings billing section.

import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { isOverUsageLimit, useWorkspace } from "@/lib/useWorkspace";

const ACTIVE_SUBSCRIPTION_STATUSES = new Set(["active", "trialing"]);

export default function UsageLimitBanner() {
  const { data } = useWorkspace();

  const needsSubscription = !!data && !ACTIVE_SUBSCRIPTION_STATUSES.has(data.subscriptionStatus);

  if (needsSubscription) {
    return (
      <div className="flex items-start gap-2 rounded-[var(--radius-md)] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        <AlertTriangle size={16} className="mt-0.5 shrink-0" />
        <span>
          Start your free trial to begin processing emails — new emails are
          landing unprocessed.{" "}
          <Link href="/settings#billing" className="font-medium underline">
            Start free trial
          </Link>
        </span>
      </div>
    );
  }

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
