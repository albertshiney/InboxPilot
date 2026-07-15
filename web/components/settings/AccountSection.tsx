"use client";

// Editable workspace name (PATCH {name}), read-only login email (passed down
// from the server component that read the NextAuth session — see
// app/(app)/settings/page.tsx), and a Delete workspace button that's a
// mailto: tooltip only for MVP (no destructive endpoint exists yet).

import { useState } from "react";
import { apiPatch } from "@/lib/api";
import SectionCard from "@/components/settings/SectionCard";
import SaveBar from "@/components/settings/SaveBar";
import { useSectionSave } from "@/components/settings/useSectionSave";

const SUPPORT_EMAIL = "support@inboxpilot.app";

export default function AccountSection({
  name,
  loginEmail,
  refresh,
}: {
  name: string;
  loginEmail: string | null;
  refresh: () => Promise<void>;
}) {
  const [value, setValue] = useState(name);
  const { saving, saved, error, save } = useSectionSave(refresh);

  function handleSave() {
    void save(() => apiPatch("settings", { name: value }));
  }

  return (
    <SectionCard id="account" title="Account" description="Workspace details.">
      <div>
        <label className="text-sm font-medium text-[var(--color-foreground)]" htmlFor="name">
          Workspace name
        </label>
        <input
          id="name"
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="mt-1.5 w-full rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-card-bg)] px-3 py-2 text-sm"
        />
      </div>

      <div>
        <p className="text-sm font-medium text-[var(--color-foreground)]">Login email</p>
        <p className="mt-1.5 text-sm text-[var(--color-muted)]">{loginEmail ?? "—"}</p>
      </div>

      <SaveBar onSave={handleSave} saving={saving} saved={saved} error={error} />

      <div className="border-t border-[var(--color-border)] pt-4">
        <button
          type="button"
          title={`To delete your workspace, email ${SUPPORT_EMAIL}`}
          onClick={() => {
            window.location.href = `mailto:${SUPPORT_EMAIL}?subject=Delete%20my%20workspace`;
          }}
          className="w-fit rounded-[var(--radius-sm)] border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50"
        >
          Delete workspace
        </button>
      </div>
    </SectionCard>
  );
}
