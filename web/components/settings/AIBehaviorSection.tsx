"use client";

// Tone preset, signature, and custom instructions — the free-text knobs that
// shape drafted replies.

import { useState } from "react";
import { apiPatch } from "@/lib/api";
import SectionCard from "@/components/settings/SectionCard";
import SaveBar from "@/components/settings/SaveBar";
import { useSectionSave } from "@/components/settings/useSectionSave";
import type { WorkspaceSettings } from "@/lib/useWorkspace";

const TONE_OPTIONS = [
  { value: "friendly", label: "Friendly" },
  { value: "professional", label: "Professional" },
  { value: "concise", label: "Concise" },
];

export default function AIBehaviorSection({
  settings,
  refresh,
}: {
  settings: WorkspaceSettings;
  refresh: () => Promise<void>;
}) {
  const [tone, setTone] = useState(settings.tone);
  const [signature, setSignature] = useState(settings.signature);
  const [customInstructions, setCustomInstructions] = useState(settings.customInstructions);
  const { saving, saved, error, save } = useSectionSave(refresh);

  function handleSave() {
    void save(() =>
      apiPatch("settings", {
        settings: { tone, signature, customInstructions },
      }),
    );
  }

  return (
    <SectionCard
      id="ai-behavior"
      title="AI behavior"
      description="Shape how drafted replies sound."
    >
      <div>
        <label className="text-sm font-medium text-[var(--color-foreground)]" htmlFor="tone">
          Tone
        </label>
        <select
          id="tone"
          value={tone}
          onChange={(e) => setTone(e.target.value)}
          className="mt-1.5 w-full rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-card-bg)] px-3 py-2 text-sm"
        >
          {TONE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label
          className="text-sm font-medium text-[var(--color-foreground)]"
          htmlFor="signature"
        >
          Signature
        </label>
        <textarea
          id="signature"
          rows={3}
          value={signature}
          onChange={(e) => setSignature(e.target.value)}
          placeholder="e.g. Best, the Acme Support team"
          className="mt-1.5 w-full resize-y rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-card-bg)] px-3 py-2 text-sm"
        />
      </div>

      <div>
        <label
          className="text-sm font-medium text-[var(--color-foreground)]"
          htmlFor="custom-instructions"
        >
          Custom instructions
        </label>
        <textarea
          id="custom-instructions"
          rows={4}
          value={customInstructions}
          onChange={(e) => setCustomInstructions(e.target.value)}
          placeholder="e.g. Always mention our 30-day return policy for refund requests."
          className="mt-1.5 w-full resize-y rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-card-bg)] px-3 py-2 text-sm"
        />
      </div>

      <SaveBar onSave={handleSave} saving={saving} saved={saved} error={error} />
    </SectionCard>
  );
}
