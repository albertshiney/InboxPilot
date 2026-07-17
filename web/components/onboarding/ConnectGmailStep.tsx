"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { apiGet } from "@/lib/api";
import Spinner from "@/components/Spinner";

// Backend allows 60 live polls/min per workspace; 2.5s leaves room for a
// second tab plus manual refreshes.
const POLL_INTERVAL_MS = 2500;

type ConnectStatus = "none" | "pending" | "active" | string;

export default function ConnectGmailStep({
  onConnected,
}: {
  onConnected: (emailAddress: string) => void;
}) {
  const [status, setStatus] = useState<ConnectStatus>("none");
  const [emailAddress, setEmailAddress] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [checking, setChecking] = useState(false);
  const [redirectUrl, setRedirectUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkStatus = useCallback(async (manual = false) => {
    if (manual) {
      setChecking(true);
      setError(null);
    }
    try {
      const data = await apiGet<{ status: ConnectStatus; emailAddress: string | null }>(
        "composio/status?live=1",
      );
      // Never demote: a user who reloads mid-flow can briefly read as
      // "none"/"pending" from a stale poll racing the OAuth completion.
      setStatus((prev) => (prev === "active" ? prev : data.status));
      if (data.status === "active") setEmailAddress(data.emailAddress);
    } catch (e) {
      // Background polls fail silently (transient network blips, 429s);
      // only a manual refresh surfaces the error.
      if (manual) {
        setError(e instanceof Error ? e.message : "Failed to check connection status");
      }
    } finally {
      if (manual) setChecking(false);
    }
  }, []);

  // Poll continuously while not connected — the user may have started the
  // OAuth flow in a previous page load, so waiting for a Connect click here
  // would leave them stuck. Skips ticks while the tab is hidden and
  // re-checks immediately when the user comes back from Google's tab.
  useEffect(() => {
    if (status === "active") return;
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
  }, [status, checkStatus]);

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
        setRedirectUrl(data.redirectUrl);
        window.open(data.redirectUrl, "_blank", "noopener,noreferrer");
      }
      setStatus("pending");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start Gmail connection");
    } finally {
      setConnecting(false);
    }
  }

  const isPending = status === "pending";

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

      {status === "active" ? (
        <div className="rounded-[var(--radius-md)] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {emailAddress ? (
            <>
              Connected as <span className="font-medium">{emailAddress}</span>
            </>
          ) : (
            "Connected"
          )}
        </div>
      ) : (
        <>
          {isPending && (
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

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void handleConnect()}
              disabled={connecting}
              className="inline-flex w-fit items-center gap-2 rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
            >
              {connecting && <Spinner size={14} />}
              {connecting
                ? "Opening Google..."
                : isPending
                  ? "Try connecting again"
                  : "Connect Gmail"}
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
          </div>
        </>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => status === "active" && onConnected(emailAddress ?? "")}
          disabled={status !== "active"}
          className="rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
        >
          Continue
        </button>
      </div>
    </div>
  );
}
