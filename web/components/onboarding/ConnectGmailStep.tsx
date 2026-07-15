"use client";

import { useEffect, useRef, useState } from "react";
import { apiGet } from "@/lib/api";

const POLL_INTERVAL_MS = 2000;

type ConnectStatus = "none" | "pending" | "active" | string;

export default function ConnectGmailStep({
  onConnected,
}: {
  onConnected: (emailAddress: string) => void;
}) {
  const [status, setStatus] = useState<ConnectStatus>("none");
  const [emailAddress, setEmailAddress] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function probeInitialStatus() {
    try {
      const data = await apiGet<{ status: ConnectStatus; emailAddress: string | null }>(
        "composio/status?live=1",
      );
      if (data.status === "active") {
        setStatus("active");
        setEmailAddress(data.emailAddress);
      }
    } catch {
      // Non-fatal: fall back to the normal connect flow if the probe fails.
    }
  }

  useEffect(() => {
    async function run() {
      await probeInitialStatus();
    }
    void run();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function pollStatus() {
    try {
      const data = await apiGet<{ status: ConnectStatus; emailAddress: string | null }>(
        "composio/status?live=1",
      );
      setStatus(data.status);
      if (data.status === "active") {
        setEmailAddress(data.emailAddress);
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to check connection status");
    }
  }

  async function handleConnect() {
    setConnecting(true);
    setError(null);
    try {
      const data = await apiGet<{
        redirectUrl?: string;
        alreadyConnected?: boolean;
        emailAddress?: string | null;
      }>("composio/connect");

      if (data.alreadyConnected) {
        setStatus("active");
        setEmailAddress(data.emailAddress ?? null);
        return;
      }

      if (data.redirectUrl) {
        window.open(data.redirectUrl, "_blank", "noopener,noreferrer");
      }
      setStatus("pending");
      await pollStatus();
      if (!pollRef.current) {
        pollRef.current = setInterval(() => void pollStatus(), POLL_INTERVAL_MS);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start Gmail connection");
    } finally {
      setConnecting(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-[var(--color-foreground)]">
          Connect your Gmail
        </h2>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          InboxPilot reads incoming support emails and drafts replies from your
          Gmail inbox. This opens Google&apos;s consent screen in a new tab.
        </p>
      </div>

      {status === "active" && emailAddress ? (
        <div className="rounded-[var(--radius-md)] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          Connected as <span className="font-medium">{emailAddress}</span>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => void handleConnect()}
          disabled={connecting || status === "pending"}
          className="w-fit rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {status === "pending"
            ? "Waiting for connection..."
            : connecting
              ? "Opening Google..."
              : "Connect Gmail"}
        </button>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => emailAddress && onConnected(emailAddress)}
          disabled={status !== "active" || !emailAddress}
          className="rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Continue
        </button>
      </div>
    </div>
  );
}
