"use client";

// Blocking 3-step onboarding wizard, gated in via app/(app)/layout.tsx —
// users land here whenever their workspace has no active Gmail connection.

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiPatch } from "@/lib/api";
import Stepper from "@/components/onboarding/Stepper";
import ConnectGmailStep from "@/components/onboarding/ConnectGmailStep";
import UploadKnowledgeStep from "@/components/onboarding/UploadKnowledgeStep";
import ChooseModeStep, { type ModeSelection } from "@/components/onboarding/ChooseModeStep";

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [finishing, setFinishing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFinish(selection: ModeSelection) {
    setFinishing(true);
    setError(null);
    try {
      await apiPatch("settings", { settings: selection });
      router.push("/dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save settings");
      setFinishing(false);
    }
  }

  return (
    <div className="flex min-h-screen items-start justify-center bg-[var(--color-app-bg)] px-4 py-12">
      <div className="w-full max-w-xl rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)] p-6 shadow-sm">
        <div className="mb-6 flex flex-col gap-1">
          <span className="text-sm font-semibold text-[var(--color-foreground)]">
            InboxPilot
          </span>
          <p className="text-xs text-[var(--color-muted)]">
            Let&apos;s get your inbox set up.
          </p>
        </div>

        <div className="mb-6">
          <Stepper current={step} />
        </div>

        {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

        {step === 1 && (
          <ConnectGmailStep onConnected={() => setStep(2)} />
        )}
        {step === 2 && <UploadKnowledgeStep onNext={() => setStep(3)} />}
        {step === 3 && (
          <ChooseModeStep onFinish={handleFinish} finishing={finishing} />
        )}
      </div>
    </div>
  );
}
