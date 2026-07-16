"use client";

// Plan + status pill, usage this month, and a single Subscribe/Manage
// billing button depending on subscription state. Also surfaces the
// `?billing=success|cancelled` query param Stripe checkout redirects back
// with (see api/app/routers/billing.py success_url/cancel_url).

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { apiPost } from "@/lib/api";
import SectionCard from "@/components/settings/SectionCard";
import Spinner from "@/components/Spinner";
import type { Workspace } from "@/lib/useWorkspace";

const USAGE_LIMIT = 500;
// Statuses for which a Stripe customer (and thus a portal session) already
// exists — route these to "Manage billing" rather than "Subscribe" so a
// past-due or canceled customer reactivates/updates payment via the portal
// instead of accidentally starting a brand-new subscription with a fresh
// trial.
const MANAGE_BILLING_STATUSES = new Set(["active", "trialing", "past_due", "canceled"]);

const STATUS_STYLES: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-700",
  trialing: "bg-emerald-50 text-emerald-700",
  past_due: "bg-amber-50 text-amber-700",
  canceled: "bg-gray-100 text-gray-600",
  none: "bg-gray-100 text-gray-600",
};

export default function BillingSection({ workspace }: { workspace: Workspace }) {
  const searchParams = useSearchParams();
  const billingNotice = searchParams.get("billing");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const shouldManageBilling = MANAGE_BILLING_STATUSES.has(workspace.subscriptionStatus);
  const usage = workspace.usage.emailsProcessedThisMonth;

  async function handleClick() {
    setLoading(true);
    setError(null);
    try {
      const path = shouldManageBilling ? "billing/portal" : "billing/checkout";
      const data = await apiPost<{ url: string }>(path);
      window.location.href = data.url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start billing session");
      setLoading(false);
    }
  }

  return (
    <SectionCard id="billing" title="Billing" description="Plan, usage, and payment method.">
      {billingNotice === "success" && (
        <p className="rounded-[var(--radius-sm)] bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          Subscription updated successfully.
        </p>
      )}
      {billingNotice === "cancelled" && (
        <p className="rounded-[var(--radius-sm)] bg-gray-100 px-3 py-2 text-sm text-gray-600">
          Checkout was cancelled — no changes made.
        </p>
      )}

      <div className="flex items-center gap-3">
        <span className="text-sm text-[var(--color-foreground)]">
          {workspace.plan ?? "No plan"}
        </span>
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
            STATUS_STYLES[workspace.subscriptionStatus] ?? STATUS_STYLES.none
          }`}
        >
          {workspace.subscriptionStatus}
        </span>
      </div>

      <p className="text-sm text-[var(--color-muted)]">
        {usage} / {USAGE_LIMIT} emails this month
      </p>

      <button
        type="button"
        onClick={() => void handleClick()}
        disabled={loading}
        className="inline-flex w-fit items-center gap-2 rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {loading && <Spinner size={14} />}
        {loading ? "Redirecting..." : shouldManageBilling ? "Manage billing" : "Subscribe"}
      </button>

      {error && <p className="text-sm text-red-600">{error}</p>}
    </SectionCard>
  );
}
