"use client";

// Shared per-section save state: each settings section calls `save(fn)` with
// its own PATCH call; this tracks saving/saved/error so every section gets
// the same "Saved" toast + inline error behavior without repeating the
// boilerplate five times.

import { useCallback, useRef, useState } from "react";

const SAVED_TOAST_MS = 2500;

export function useSectionSave(refresh: () => Promise<void>) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const save = useCallback(
    async (fn: () => Promise<unknown>) => {
      setSaving(true);
      setError(null);
      setSaved(false);
      try {
        await fn();
        await refresh();
        setSaved(true);
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        timeoutRef.current = setTimeout(() => setSaved(false), SAVED_TOAST_MS);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to save");
      } finally {
        setSaving(false);
      }
    },
    [refresh],
  );

  return { saving, saved, error, save };
}
