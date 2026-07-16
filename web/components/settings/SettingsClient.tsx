"use client";

// Tabbed settings page (Inbox / Billing / Account) — one section visible at
// a time, selected via the `?tab=` query param so links and back/forward
// work. Shares one `useWorkspace()` fetch across all sections; each section
// PATCHes independently and calls `refresh()` to pull the merged doc back
// down. AI behavior and automation live on the /ai-behavior page.

import { useRouter, useSearchParams } from "next/navigation";
import { useWorkspace } from "@/lib/useWorkspace";
import { PageLoader } from "@/components/Spinner";
import InboxSection from "@/components/settings/InboxSection";
import BillingSection from "@/components/settings/BillingSection";
import AccountSection from "@/components/settings/AccountSection";

const TABS = [
  { id: "inbox", label: "Inbox" },
  { id: "billing", label: "Billing" },
  { id: "account", label: "Account" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function isTabId(value: string | null): value is TabId {
  return TABS.some((tab) => tab.id === value);
}

export default function SettingsClient({ loginEmail }: { loginEmail: string | null }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data, loading, error, refresh } = useWorkspace();

  const tabParam = searchParams.get("tab");
  // Stripe checkout redirects back to /settings?billing=success|cancelled
  // without a tab param — land on Billing so the notice is visible.
  const activeTab: TabId = isTabId(tabParam)
    ? tabParam
    : searchParams.get("billing")
      ? "billing"
      : "inbox";

  function selectTab(tab: TabId) {
    const params = new URLSearchParams(searchParams);
    params.set("tab", tab);
    router.replace(`/settings?${params.toString()}`, { scroll: false });
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight text-[var(--color-foreground)] sm:text-3xl">
          Settings
        </h1>
        <p className="mt-1 text-[15px] text-[var(--color-muted)]">
          Your inbox connection, billing, and account.
        </p>
      </div>

      <nav className="scrollbar-none flex gap-1 overflow-x-auto border-b border-[var(--color-border)]">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => selectTab(tab.id)}
            className={`-mb-px whitespace-nowrap border-b-2 px-4 py-2.5 text-[15px] font-medium transition-colors ${
              activeTab === tab.id
                ? "border-[var(--color-accent)] text-[var(--color-foreground)]"
                : "border-transparent text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {loading && !data && <PageLoader label="Loading settings" />}

      {data && (
        <div className="flex flex-col gap-6">
          {activeTab === "inbox" && (
            <InboxSection connection={data.connection} refresh={refresh} />
          )}
          {activeTab === "billing" && <BillingSection workspace={data} />}
          {activeTab === "account" && (
            <AccountSection name={data.name} loginEmail={loginEmail} refresh={refresh} />
          )}
        </div>
      )}
    </div>
  );
}
