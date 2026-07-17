"use client";

// Standalone paywall page for users who finished Gmail onboarding but never
// started a subscription. Every (app) route redirects here (see
// app/(app)/layout.tsx) until the workspace is active/trialing, so this
// reuses onboarding's StartTrialStep card as the single checkout entry point.

import { useRouter } from "next/navigation";
import Logo from "@/components/Logo";
import StartTrialStep from "@/components/onboarding/StartTrialStep";

export default function StartTrialPage() {
  const router = useRouter();
  return (
    <div className="flex min-h-screen items-start justify-center bg-[var(--color-app-bg)] px-4 py-10 sm:py-16">
      <div className="anim-rise w-full max-w-xl rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-white p-6 shadow-[var(--shadow-raised)] sm:p-8">
        <div className="mb-7 flex flex-col gap-2">
          <Logo size={30} />
          <p className="text-[15px] text-[var(--color-muted)]">
            One last step before your inbox goes live.
          </p>
        </div>
        <StartTrialStep onContinue={() => router.push("/dashboard")} />
      </div>
    </div>
  );
}
