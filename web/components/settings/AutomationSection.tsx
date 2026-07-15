"use client";

// Autopilot toggle, confidence threshold slider (50-99), blocked-categories
// multi-select, and the static loop-prevention note.

import { useState } from "react";
import { apiPatch } from "@/lib/api";
import SectionCard from "@/components/settings/SectionCard";
import SaveBar from "@/components/settings/SaveBar";
import { useSectionSave } from "@/components/settings/useSectionSave";
import type { WorkspaceSettings } from "@/lib/useWorkspace";

const CATEGORY_OPTIONS: { value: string; label: string }[] = [
  { value: "billing", label: "Billing" },
  { value: "technical", label: "Technical" },
  { value: "shipping", label: "Shipping" },
  { value: "account", label: "Account" },
  { value: "refund", label: "Refund" },
  { value: "other", label: "Other" },
];

export default function AutomationSection({
  settings,
  refresh,
}: {
  settings: WorkspaceSettings;
  refresh: () => Promise<void>;
}) {
  const [autopilot, setAutopilot] = useState(settings.autopilot);
  const [threshold, setThreshold] = useState(settings.confidenceThreshold);
  const [blocked, setBlocked] = useState<string[]>(settings.blockedCategories);
  const { saving, saved, error, save } = useSectionSave(refresh);

  function toggleCategory(value: string) {
    setBlocked((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value],
    );
  }

  function handleSave() {
    void save(() =>
      apiPatch("settings", {
        settings: {
          autopilot,
          confidenceThreshold: threshold,
          blockedCategories: blocked,
        },
      }),
    );
  }

  return (
    <SectionCard
      id="automation"
      title="Automation"
      description="Control when InboxPilot sends replies without you."
    >
      <label className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-[var(--color-foreground)]">Autopilot</p>
          <p className="text-sm text-[var(--color-muted)]">
            Automatically send replies that meet the confidence threshold.
          </p>
        </div>
        <input
          type="checkbox"
          checked={autopilot}
          onChange={(e) => setAutopilot(e.target.checked)}
          className="h-5 w-9 shrink-0 accent-[var(--color-accent)]"
        />
      </label>

      <div>
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-[var(--color-foreground)]">
            Confidence threshold
          </p>
          <span className="text-sm text-[var(--color-muted)]">{threshold}%</span>
        </div>
        <input
          type="range"
          min={50}
          max={99}
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
          className="mt-2 w-full accent-[var(--color-accent)]"
        />
      </div>

      <div>
        <p className="text-sm font-medium text-[var(--color-foreground)]">
          Blocked categories
        </p>
        <p className="text-sm text-[var(--color-muted)]">
          Emails in these categories are never auto-sent, regardless of confidence.
        </p>
        <div className="mt-2 flex flex-wrap gap-3">
          {CATEGORY_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className="flex items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--color-border)] px-3 py-1.5 text-sm"
            >
              <input
                type="checkbox"
                checked={blocked.includes(opt.value)}
                onChange={() => toggleCategory(opt.value)}
                className="accent-[var(--color-accent)]"
              />
              {opt.label}
            </label>
          ))}
        </div>
      </div>

      <p className="rounded-[var(--radius-sm)] bg-[var(--color-app-bg)] px-3 py-2 text-sm text-[var(--color-muted)]">
        When a customer replies to an automated response, the next reply always goes to a
        human.
      </p>

      <SaveBar onSave={handleSave} saving={saving} saved={saved} error={error} />
    </SectionCard>
  );
}
