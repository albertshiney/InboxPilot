import { Mail, BookOpenCheck, ShieldCheck } from "lucide-react";

const FEATURES = [
  {
    icon: Mail,
    title: "Connect Gmail in one click",
    body: "Point InboxPilot at your support inbox and it starts reading incoming email immediately — no forwarding rules, no migration.",
  },
  {
    icon: BookOpenCheck,
    title: "Answers grounded in your docs",
    body: "Upload your help center, policies, or FAQs. Every draft cites what your team actually says — not a generic guess.",
  },
  {
    icon: ShieldCheck,
    title: "Autopilot with guardrails",
    body: "Only high-confidence replies get sent automatically. Anything uncertain lands in your review queue for a one-click approval.",
  },
];

export default function FeatureBlurbs() {
  return (
    <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
      <h2 className="sr-only">Features</h2>
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
        {FEATURES.map(({ icon: Icon, title, body }) => (
          <div
            key={title}
            className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)] p-6 shadow-sm"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--color-accent-soft)]">
              <Icon className="h-4.5 w-4.5 text-[var(--color-accent)]" />
            </div>
            <h3 className="mt-4 text-sm font-semibold text-[var(--color-foreground)]">
              {title}
            </h3>
            <p className="mt-2 text-sm text-[var(--color-muted)]">{body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
