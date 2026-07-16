import { Mail, BookOpenCheck, Send } from "lucide-react";
import Reveal from "./Reveal";

// A real sequence — connect, ground, autopilot — so the numbered steps
// carry information, not decoration.
const STEPS = [
  {
    number: "01",
    icon: Mail,
    title: "Connect your Gmail inbox",
    body: "Point InboxPilot at your support address and it starts reading incoming email immediately — no forwarding rules, no migration.",
  },
  {
    number: "02",
    icon: BookOpenCheck,
    title: "Ground it in your docs",
    body: "Upload your help center, policies, or FAQs. Every draft cites what your team actually says — not a generic guess.",
  },
  {
    number: "03",
    icon: Send,
    title: "Review — or engage Autopilot",
    body: "Approve drafts with one click. When you're ready, let Autopilot send the high-confidence replies on its own, inside your guardrails.",
  },
];

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="border-y border-[var(--color-border)] bg-white">
      <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 sm:py-28">
        <Reveal>
          <p className="text-sm font-semibold uppercase tracking-[0.14em] text-[var(--color-accent)]">
            How it works
          </p>
          <h2 className="font-display mt-3 max-w-2xl text-balance text-3xl font-semibold tracking-tight text-[var(--color-foreground)] sm:text-4xl">
            From first email to autopilot in an afternoon
          </h2>
        </Reveal>

        <div className="mt-12 grid grid-cols-1 gap-10 sm:mt-16 sm:grid-cols-3 sm:gap-8">
          {STEPS.map(({ number, icon: Icon, title, body }, i) => (
            <Reveal key={number} delay={i * 120}>
              <div className="relative">
                <div className="flex items-center gap-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-accent-soft)]">
                    <Icon className="h-5 w-5 text-[var(--color-accent)]" />
                  </div>
                  <span className="readout text-sm font-medium text-[var(--color-faint)]">
                    {number}
                  </span>
                  {i < STEPS.length - 1 && (
                    <span
                      aria-hidden="true"
                      className="hidden h-px flex-1 border-t border-dashed border-[var(--color-border-strong)] sm:block"
                    />
                  )}
                </div>
                <h3 className="mt-5 text-lg font-semibold text-[var(--color-foreground)]">
                  {title}
                </h3>
                <p className="mt-2.5 text-[15px] leading-relaxed text-[var(--color-muted)]">
                  {body}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
