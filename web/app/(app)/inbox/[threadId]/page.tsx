"use client";

// Thread two-pane view: ThreadMessages on the left, DraftPanel on the
// right. Approve/discard are optimistic — they navigate back to the inbox
// immediately and let the request finish in the background, since the
// user has already moved on.

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { apiGet, apiPost } from "@/lib/api";
import ThreadMessages, { type ThreadMessage } from "@/components/ThreadMessages";
import DraftPanel, { type Draft } from "@/components/DraftPanel";

type ThreadDetail = {
  id: string;
  subject: string;
  customerName: string | null;
  customerEmail: string | null;
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
    router.push("/inbox");
    await apiPost(`threads/${threadId}/approve`, { body });
  }

  async function handleRegenerate(instruction?: string) {
    const updated = await apiPost<Draft>(`threads/${threadId}/regenerate`, { instruction });
    setThread((prev) => (prev ? { ...prev, draft: updated } : prev));
  }

  async function handleDiscard() {
    router.push("/inbox");
    await apiPost(`threads/${threadId}/discard`);
  }

  if (loading) {
    return <p className="text-sm text-[var(--color-muted)]">Loading...</p>;
  }

  if (error || !thread) {
    return <p className="text-sm text-red-600">{error || "Thread not found"}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <button
        type="button"
        onClick={() => router.push("/inbox")}
        className="flex w-fit items-center gap-1.5 text-sm text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
      >
        <ArrowLeft size={14} />
        Back to inbox
      </button>

      <div>
        <h1 className="text-lg font-semibold text-[var(--color-foreground)]">{thread.subject}</h1>
        <p className="text-sm text-[var(--color-muted)]">
          {thread.customerName || thread.customerEmail}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)] p-4">
          <ThreadMessages messages={thread.messages} />
        </div>
        <DraftPanel
          draft={thread.draft}
          onApprove={handleApprove}
          onRegenerate={handleRegenerate}
          onDiscard={handleDiscard}
        />
      </div>
    </div>
  );
}
