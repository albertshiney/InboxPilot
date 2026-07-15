"use client";

// Connected Gmail address + status pill, Reconnect (re-runs the same
// GET /composio/connect + poll flow as onboarding's ConnectGmailStep) and
// Disconnect (new DELETE /composio/connection route).

import { useEffect, useRef, useState } from "react";
import { apiDelete, apiGet } from "@/lib/api";
import SectionCard from "@/components/settings/SectionCard";
import type { WorkspaceConnection } from "@/lib/useWorkspace";

const POLL_INTERVAL_MS = 2000;

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
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function pollUntilActive() {
    try {
      const data = await apiGet<{ status: string }>("composio/status?live=1");
      if (data.status === "active") {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
        await refresh();
        setConnecting(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to check connection status");
    }
  }

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
        window.open(data.redirectUrl, "_blank", "noopener,noreferrer");
      }
      if (!pollRef.current) {
        pollRef.current = setInterval(() => void pollUntilActive(), POLL_INTERVAL_MS);
      }
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

  const status = connection?.status ?? "none";
  const isActive = status === "active";

  return (
    <SectionCard id="inbox" title="Inbox" description="Your connected Gmail account.">
      <div className="flex items-center gap-3">
        <span className="text-sm text-[var(--color-foreground)]">
          {connection?.emailAddress ?? (isActive ? "Connected" : "Not connected")}
        </span>
        <StatusPill status={status} />
      </div>

      <div className="flex gap-3">
        <button
          type="button"
          onClick={() => void handleReconnect()}
          disabled={connecting}
          className="w-fit rounded-[var(--radius-sm)] border border-[var(--color-border)] px-4 py-2 text-sm font-medium text-[var(--color-foreground)] hover:bg-[var(--color-app-bg)] disabled:opacity-50"
        >
          {connecting ? "Waiting for connection..." : "Reconnect"}
        </button>
        {isActive && (
          <button
            type="button"
            onClick={() => void handleDisconnect()}
            disabled={disconnecting}
            className="w-fit rounded-[var(--radius-sm)] border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
          >
            {disconnecting ? "Disconnecting..." : "Disconnect"}
          </button>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
    </SectionCard>
  );
}
