// Chronological message bubbles for the thread two-pane view: customer
// messages align left on a white bubble, anything sent by us (AI-auto or a
// human-approved reply) aligns right on an indigo-tinted bubble.

export type ThreadMessage = {
  id: string;
  from: string;
  sentBy: "customer" | "ai_auto" | "human_approved";
  bodyText: string;
  receivedAt: string;
};

const SENDER_LABELS: Record<ThreadMessage["sentBy"], string> = {
  customer: "Customer",
  ai_auto: "AI (auto-sent)",
  human_approved: "You",
};

function formatTimestamp(value: string): string {
  try {
    return new Date(value).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

export default function ThreadMessages({ messages }: { messages: ThreadMessage[] }) {
  if (messages.length === 0) {
    return <p className="text-sm text-[var(--color-muted)]">No messages yet.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      {messages.map((m) => {
        const outbound = m.sentBy !== "customer";
        return (
          <div key={m.id} className={`flex ${outbound ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-[var(--radius-md)] border px-4 py-2.5 text-sm ${
                outbound
                  ? "border-[var(--color-accent-soft)] bg-[var(--color-accent-soft)] text-[var(--color-foreground)]"
                  : "border-[var(--color-border)] bg-white text-[var(--color-foreground)]"
              }`}
            >
              <div className="mb-1.5 flex items-center gap-2 text-xs text-[var(--color-muted)]">
                <span className="font-medium">{SENDER_LABELS[m.sentBy] ?? m.from}</span>
                <span className="readout text-[11px] text-[var(--color-faint)]">
                  {formatTimestamp(m.receivedAt)}
                </span>
              </div>
              <p className="whitespace-pre-wrap">{m.bodyText}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
