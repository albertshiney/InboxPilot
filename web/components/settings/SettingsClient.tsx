"use client";

// Single settings page with an anchored sub-nav (Inbox / Automation /
// AI behavior / Billing / Account). Shares one `useWorkspace()` fetch across
// all sections; each section PATCHes independently and calls `refresh()` to
// pull the merged doc back down.

import { Suspense } from "react";
import { useWorkspace } from "@/lib/useWorkspace";
import InboxSection from "@/components/settings/InboxSection";
import AutomationSection from "@/components/settings/AutomationSection";
import AIBehaviorSection from "@/components/settings/AIBehaviorSection";
import BillingSection from "@/components/settings/BillingSection";
import AccountSection from "@/components/settings/AccountSection";

const NAV_ITEMS = [
  { href: "#inbox", label: "Inbox" },
  { href: "#automation", label: "Automation" },
  { href: "#ai-behavior", label: "AI behavior" },
  { href: "#billing", label: "Billing" },
  { href: "#account", label: "Account" },
];

export default function SettingsClient({ loginEmail }: { loginEmail: string | null }) {
  const { data, loading, error, refresh } = useWorkspace();

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-[var(--color-foreground)]">Settings</h1>

      <nav className="flex gap-1 border-b border-[var(--color-border)]">
        {NAV_ITEMS.map((item) => (
          <a
            key={item.href}
            href={item.href}
            className="px-3 py-2 text-sm font-medium text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
          >
            {item.label}
          </a>
        ))}
      </nav>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {loading && !data && (
        <p className="text-sm text-[var(--color-muted)]">Loading settings...</p>
      )}

      {data && (
        <div className="flex flex-col gap-6">
          <InboxSection connection={data.connection} refresh={refresh} />
          <AutomationSection settings={data.settings} refresh={refresh} />
          <AIBehaviorSection settings={data.settings} refresh={refresh} />
          <Suspense fallback={null}>
            <BillingSection workspace={data} />
          </Suspense>
          <AccountSection name={data.name} loginEmail={loginEmail} refresh={refresh} />
        </div>
      )}
    </div>
  );
}
