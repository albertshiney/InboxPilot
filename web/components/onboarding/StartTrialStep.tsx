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
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-2xl font-semibold tracking-tight text-[var(--color-foreground)]">
          Try InboxPilot free for 7 days
        </h2>
        <p className="mt-1.5 text-sm text-[var(--color-muted)]">
          Full access from today. Your card won&apos;t be charged until the
          trial ends, and you can cancel anytime before then.
        </p>
      </div>

      <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-accent-soft)] px-5 py-4">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="readout text-3xl font-semibold text-[var(--color-foreground)]">
            $49
          </span>
          <span className="text-sm text-[var(--color-muted)]">/month after your trial</span>
        </div>
        <p className="mt-1 text-sm text-[var(--color-foreground)]">
          <span className="readout">500</span> support emails processed and
          drafted every month.
        </p>
      </div>

      {/* Trial timeline — the dashed flight path from today to day 7. */}
      <ol className="flex flex-col">
        <li className="relative flex gap-3.5 pb-6">
          <span
            aria-hidden
            className="absolute bottom-0 left-[5px] top-4 border-l border-dashed border-[var(--color-accent)]"
          />
          <span className="relative z-10 mt-1 h-[11px] w-[11px] shrink-0 rounded-full bg-[var(--color-accent)]" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-[var(--color-foreground)]">
              Today — full access
            </p>
            <p className="mt-0.5 text-sm text-[var(--color-muted)]">
              InboxPilot starts reading incoming support emails and drafting
              replies right away.
            </p>
          </div>
        </li>
        <li className="flex gap-3.5">
          <span className="mt-1 h-[11px] w-[11px] shrink-0 rounded-full border-2 border-[var(--color-accent)] bg-white" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-[var(--color-foreground)]">
              <span className="readout">Day 7</span> — your plan begins
            </p>
            <p className="mt-0.5 text-sm text-[var(--color-muted)]">
              First charge of <span className="readout">$49</span>, unless you
              cancel first. We keep it that simple.
            </p>
          </div>
        </li>
      </ol>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex flex-col gap-2.5">
        <button
          type="button"
          onClick={() => void handleStartTrial()}
          disabled={loading}
          className="inline-flex w-full items-center justify-center gap-2 rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-4 py-2.5 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
        >
          {loading && <Spinner size={14} />}
          {loading ? "Redirecting..." : "Start free trial"}
        </button>
        <p className="text-center text-xs text-[var(--color-muted)]">
          <span className="readout">$0</span> due today · Card required ·
          Secure checkout via Stripe
        </p>
      </div>
    </div>
  );
}
