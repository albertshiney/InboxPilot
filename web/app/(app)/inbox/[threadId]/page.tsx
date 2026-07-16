"use client";

// Thread two-pane view: ThreadMessages on the left, DraftPanel on the
// right. Approve/discard await the request before navigating back to the
// inbox — DraftPanel shows a "Sending…" state on the button while the
// request is in flight, and renders the error inline (without navigating)
// if it fails, so a failed send is never silently lost.

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { apiGet, apiPost } from "@/lib/api";
import ThreadMessages, { type ThreadMessage } from "@/components/ThreadMessages";
import DraftPanel, { type Draft } from "@/components/DraftPanel";
import { PageLoader } from "@/components/Spinner";

type ThreadDetail = {
  id: string;
  subject: string;
  customerName: string | null;
  customerEmail: string | null;
  status: string;
  messages: ThreadMessage[];
  draft: Draft | null;
};

export default function ThreadPage() {
  const params = useParams<{ threadId: string }>();
  const router = useRouter();
  const threadId = params.threadId;

  const [thread, setThread] = useState<ThreadDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await apiGet<ThreadDetail>(`threads/${threadId}`);
      setThread(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load thread");
    } finally {
      setLoading(false);
    }
  }, [threadId]);

  useEffect(() => {
    async function run() {
      await load();
    }
    void run();
  }, [load]);

  async function handleApprove(body?: string) {
    await apiPost(`threads/${threadId}/approve`, { body });
    router.push("/inbox");
  }

  async function handleRegenerate(instruction?: string) {
    await apiPost<Draft>(`threads/${threadId}/regenerate`, { instruction });
    await load();
  }

  async function handleDiscard() {
    await apiPost(`threads/${threadId}/discard`);
    router.push("/inbox");
  }

  if (loading) {
    return <PageLoader label="Loading thread" />;
  }

  if (error || !thread) {
    return <p className="text-sm text-red-600">{error || "Thread not found"}</p>;
  }

  return (
    <div className="flex flex-col gap-5">
      <button
        type="button"
        onClick={() => router.push("/inbox")}
        className="flex w-fit items-center gap-1.5 text-sm font-medium text-[var(--color-muted)] transition-colors hover:text-[var(--color-foreground)]"
      >
        <ArrowLeft size={15} />
        Back to inbox
      </button>

      <div>
        <h1 className="font-display text-xl font-semibold tracking-tight text-[var(--color-foreground)] sm:text-2xl">
          {thread.subject}
        </h1>
        <p className="mt-1 text-[15px] text-[var(--color-muted)]">
          {thread.customerName || thread.customerEmail}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white p-5 shadow-[var(--shadow-card)]">
          <ThreadMessages messages={thread.messages} />
        </div>
        <DraftPanel
          draft={thread.draft}
          threadStatus={thread.status}
          onApprove={handleApprove}
          onRegenerate={handleRegenerate}
          onDiscard={handleDiscard}
        />
      </div>
    </div>
  );
}
