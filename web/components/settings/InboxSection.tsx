"use client";

// Connected Gmail address + status pill, Reconnect (re-runs the same
// GET /composio/connect + poll flow as onboarding's ConnectGmailStep) and
// Disconnect (new DELETE /composio/connection route).

import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { apiDelete, apiGet } from "@/lib/api";
import SectionCard from "@/components/settings/SectionCard";
import type { WorkspaceConnection } from "@/lib/useWorkspace";
import Spinner from "@/components/Spinner";

// Backend allows 60 live polls/min per workspace; 2.5s leaves room for a
// second tab plus manual refreshes.
const POLL_INTERVAL_MS = 2500;

const STATUS_STYLES: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-700",
  pending: "bg-amber-50 text-amber-700",
  disconnected: "bg-gray-100 text-gray-600",
  none: "bg-gray-100 text-gray-600",
};

function StatusPill({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        STATUS_STYLES[status] ?? STATUS_STYLES.none
      }`}
    >
      {status}
    </span>
  );
}

export default function InboxSection({
  connection,
  refresh,
}: {
  connection: WorkspaceConnection;
  refresh: () => Promise<void>;
}) {
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [checking, setChecking] = useState(false);
  const [redirectUrl, setRedirectUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const status = connection?.status ?? "none";
  const isActive = status === "active";
  // Poll while a connect flow is in flight in this page load OR the stored
  // connection is pending (the user may have started OAuth elsewhere and
  // navigated here) — not on resting states like "none"/"disconnected".
  const waiting = connecting || status === "pending";

  const checkStatus = useCallback(
    async (manual = false) => {
      if (manual) {
        setChecking(true);
        setError(null);
      }
      try {
        const data = await apiGet<{ status: string }>("composio/status?live=1");
        if (data.status === "active") {
          setConnecting(false);
          setRedirectUrl(null);
        }
        // Manual refreshes always resync the parent workspace; background
        // polls only on the transition to active.
        if (manual || data.status === "active") await refresh();
      } catch (e) {
        // Background polls fail silently (transient network blips, 429s);
        // only a manual refresh surfaces the error.
        if (manual) {
          setError(e instanceof Error ? e.message : "Failed to check connection status");
        }
      } finally {
        if (manual) setChecking(false);
      }
    },
    [refresh],
  );

  // Skips ticks while the tab is hidden and re-checks immediately when the
  // user comes back from Google's consent tab.
  useEffect(() => {
    if (!waiting) return;
    const tick = () => {
      if (document.visibilityState === "visible") void checkStatus();
    };
    const immediate = setTimeout(tick, 0);
    const interval = setInterval(tick, POLL_INTERVAL_MS);
    document.addEventListener("visibilitychange", tick);
    window.addEventListener("focus", tick);
    return () => {
      clearTimeout(immediate);
      clearInterval(interval);
      document.removeEventListener("visibilitychange", tick);
      window.removeEventListener("focus", tick);
    };
  }, [waiting, checkStatus]);

  async function handleReconnect() {
    setConnecting(true);
    setError(null);
    try {
      const data = await apiGet<{
        redirectUrl?: string;
        alreadyConnected?: boolean;
      }>("composio/connect");

      if (data.alreadyConnected) {
        await refresh();
        setConnecting(false);
        return;
      }

      if (data.redirectUrl) {
        setRedirectUrl(data.redirectUrl);
        window.open(data.redirectUrl, "_blank", "noopener,noreferrer");
      }
      // `connecting` stays true — the polling effect flips it off once the
      // connection goes active.
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start Gmail connection");
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    setDisconnecting(true);
    setError(null);
    try {
      await apiDelete("composio/connection");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to disconnect");
    } finally {
      setDisconnecting(false);
    }
  }

  return (
    <SectionCard id="inbox" title="Inbox" description="Your connected Gmail account.">
      <div className="flex items-center gap-3">
        <span className="text-sm text-[var(--color-foreground)]">
          {connection?.emailAddress ?? (isActive ? "Connected" : "Not connected")}
        </span>
        <StatusPill status={status} />
      </div>

      {waiting && (
        <div className="flex items-center gap-2.5 rounded-[var(--radius-md)] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
          <Spinner size={14} />
          <span>
            Waiting for Google — finish signing in on the other tab.{" "}
            {redirectUrl && (
              <a
                href={redirectUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium underline underline-offset-2"
              >
                Reopen the sign-in page
              </a>
            )}
          </span>
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => void handleReconnect()}
          disabled={connecting}
          className="inline-flex w-fit items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--color-border)] px-4 py-2 text-sm font-medium text-[var(--color-foreground)] hover:bg-[var(--color-app-bg)] disabled:opacity-50"
        >
          {connecting && <Spinner size={14} />}
          {connecting ? "Waiting for connection..." : "Reconnect"}
        </button>
        <button
          type="button"
          onClick={() => void checkStatus(true)}
          disabled={checking}
          className="inline-flex w-fit items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--color-border)] px-4 py-2 text-sm font-medium text-[var(--color-foreground)] hover:bg-[var(--color-app-bg)] disabled:opacity-50"
        >
          <RefreshCw size={14} className={checking ? "animate-spin" : undefined} />
          {checking ? "Checking..." : "Refresh status"}
        </button>
        {isActive && (
          <button
            type="button"
            onClick={() => void handleDisconnect()}
            disabled={disconnecting}
            className="inline-flex w-fit items-center gap-2 rounded-[var(--radius-sm)] border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
          >
            {disconnecting && <Spinner size={14} />}
            {disconnecting ? "Disconnecting..." : "Disconnect"}
          </button>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
    </SectionCard>
  );
}
