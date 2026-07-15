"use client";

// Tiny shared hook around GET /settings. SWR-style: fetch once on mount,
// expose { data, loading, error, refresh }. Used by the settings page (to
// seed its sections) and by the usage-limit banner on Inbox + Dashboard (to
// decide whether to render at all) so both read from one shape instead of
// each re-deriving it from a separate fetch.

import { useCallback, useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

export type WorkspaceSettings = {
  autopilot: boolean;
  confidenceThreshold: number;
  tone: string;
  signature: string;
  blockedCategories: string[];
  customInstructions: string;
};

export type WorkspaceConnection = {
  emailAddress: string;
  status: string;
} | null;

export type Workspace = {
  name: string;
  settings: WorkspaceSettings;
  plan: string | null;
  subscriptionStatus: string;
  trialEndsAt: string | null;
  usage: { emailsProcessedThisMonth: number };
  connection: WorkspaceConnection;
};

const USAGE_LIMIT = 500;

export function isOverUsageLimit(workspace: Workspace | null): boolean {
  return (workspace?.usage?.emailsProcessedThisMonth ?? 0) >= USAGE_LIMIT;
}

export function useWorkspace() {
  const [data, setData] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const workspace = await apiGet<Workspace>("settings");
      setData(workspace);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load workspace settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    async function run() {
      await refresh();
    }
    void run();
  }, [refresh]);

  return { data, loading, error, refresh };
}

export { USAGE_LIMIT };
