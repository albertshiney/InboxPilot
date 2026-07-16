"use client";

// Final, non-skippable onboarding step: card-required 7-day trial (task 15
// — email processing requires an active/trialing subscription, so a
// workspace can't finish onboarding without starting one). Probes GET
// /settings on mount in case the workspace already has an active/trialing
// subscription (e.g. they subscribed in another tab, or came back from a
// completed Stripe checkout) so they aren't sent through checkout again.

import { useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import type { Workspace } from "@/lib/useWorkspace";
import Spinner from "@/components/Spinner";

const ACTIVE_STATUSES = new Set(["active", "trialing"]);

export default function StartTrialStep({ onContinue }: { onContinue: () => void }) {
  const [checking, setChecking] = useState(true);
  const [alreadyActive, setAlreadyActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function probe() {
      try {
        const workspace = await apiGet<Workspace>("settings");
        if (ACTIVE_STATUSES.has(workspace.subscriptionStatus)) {
          setAlreadyActive(true);
        }
      } catch {
        // Non-fatal: fall back to the normal start-trial flow if the probe fails.
      } finally {
        setChecking(false);
      }
    }
    void probe();
  }, []);

  async function handleStartTrial() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiPost<{ url: string }>("billing/checkout");
      window.location.href = data.url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start checkout");
      setLoading(false);
    }
  }

  if (checking) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm text-[var(--color-muted)]">Checking your subscription...</p>
      </div>
    );
  }

  if (alreadyActive) {
    return (
      <div className="flex flex-col gap-4">
        <div>
          <h2 className="text-lg font-semibold text-[var(--color-foreground)]">
            Start your free trial
          </h2>
        </div>
        <div className="rounded-[var(--radius-md)] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">
          Trial active
        </div>
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onContinue}
            className="rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white"
          >
            Continue
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-[var(--color-foreground)]">
          Start your free trial
        </h2>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          InboxPilot is $49/mo for 500 processed emails a month. Try it free
          for 7 days — a card is required to start the trial, but you
          won&apos;t be charged until it ends, and you can cancel anytime.
          Email processing doesn&apos;t begin until your trial starts.
        </p>
      </div>

      <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)] px-4 py-3">
        <ul className="flex flex-col gap-1.5 text-sm text-[var(--color-foreground)]">
          <li>$49/month</li>
          <li>500 emails processed per month</li>
          <li>7-day free trial — card required</li>
          <li>Cancel anytime</li>
        </ul>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => void handleStartTrial()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {loading && <Spinner size={14} />}
          {loading ? "Redirecting..." : "Start free trial"}
        </button>
      </div>
    </div>
  );
}
