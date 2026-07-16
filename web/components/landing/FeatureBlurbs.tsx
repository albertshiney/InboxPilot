import { ShieldCheck, FileSearch, GaugeCircle, Inbox } from "lucide-react";
import Reveal from "./Reveal";

const FEATURES = [
  {
    icon: FileSearch,
    title: "Every draft shows its sources",
    body: "Each reply links back to the exact passages in your docs it was written from, so reviewing takes seconds — not spelunking.",
  },
  {
    icon: GaugeCircle,
    title: "Confidence scoring on everything",
    body: "Every draft carries a confidence score. High scores can auto-send; anything uncertain waits for a human.",
  },
  {
    icon: Inbox,
    title: "A review queue, not another inbox",
    body: "One list of what actually needs you, with one-click approval and keyboard shortcuts for clearing it fast.",
  },
];

export default function FeatureBlurbs() {
  return (
    <section id="features" className="mx-auto max-w-6xl px-5 py-20 sm:px-8 sm:py-28">
      <Reveal>
        <p className="text-sm font-semibold uppercase tracking-[0.14em] text-[var(--color-accent)]">
          Built for trust
        </p>
        <h2 className="font-display mt-3 max-w-2xl text-balance text-3xl font-semibold tracking-tight text-[var(--color-foreground)] sm:text-4xl">
          Automation you can actually leave running
        </h2>
      </Reveal>

      {/* Guardrails highlight: the product's core promise gets the wide card. */}
      <Reveal delay={100}>
        <div className="mt-12 grid grid-cols-1 overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] lg:grid-cols-2">
          <div className="p-8 sm:p-10">
            <div className="flex h-12 w-12 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-accent-soft)]">
              <ShieldCheck className="h-5 w-5 text-[var(--color-accent)]" />
            </div>
            <h3 className="mt-6 text-xl font-semibold text-[var(--color-foreground)]">
              Autopilot with guardrails
            </h3>
            <p className="mt-3 max-w-md text-[15px] leading-relaxed text-[var(--color-muted)]">
              You set the confidence threshold. Replies above it send
              automatically; everything below lands in your review queue.
              Nothing leaves your inbox that your rules didn&apos;t allow.
            </p>
          </div>

          <div
            aria-hidden="true"
            className="flex items-center justify-center border-t border-[var(--color-border)] bg-[var(--color-app-bg)] p-8 sm:p-10 lg:border-l lg:border-t-0"
          >
            <div className="w-full max-w-sm rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white p-6 shadow-[var(--shadow-card)]">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium text-[var(--color-foreground)]">
                  Auto-send threshold
                </span>
                <span className="readout rounded-full bg-[var(--color-accent-soft)] px-2.5 py-1 text-xs font-medium text-[var(--color-accent)]">
                  85%
                </span>
              </div>
              <div className="relative mt-4 h-2 rounded-full bg-[var(--color-app-bg)] ring-1 ring-inset ring-[var(--color-border)]">
                <div className="absolute inset-y-0 left-0 w-[85%] rounded-full bg-gradient-to-r from-[#6366F1] to-[#4F46E5]" />
                <div className="absolute -top-1 left-[85%] h-4 w-4 -translate-x-1/2 rounded-full border-2 border-[var(--color-accent)] bg-white shadow" />
              </div>
              <div className="readout mt-5 flex flex-col gap-2.5 text-xs">
                <div className="flex items-center justify-between rounded-lg bg-emerald-50 px-3 py-2 text-emerald-700">
                  <span>92% · Refund policy</span>
                  <span className="font-medium">auto-sent</span>
                </div>
                <div className="flex items-center justify-between rounded-lg bg-amber-50 px-3 py-2 text-amber-700">
                  <span>64% · Billing dispute</span>
                  <span className="font-medium">held for review</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Reveal>

      <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-3">
        {FEATURES.map(({ icon: Icon, title, body }, i) => (
          <Reveal key={title} delay={i * 100}>
            <div className="group h-full rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-white p-7 shadow-[var(--shadow-card)] transition-all duration-300 hover:-translate-y-1 hover:shadow-[var(--shadow-raised)]">
              <div className="flex h-11 w-11 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-accent-soft)] transition-colors group-hover:bg-[var(--color-accent)] group-hover:[&>svg]:text-white">
                <Icon className="h-5 w-5 text-[var(--color-accent)] transition-colors" />
              </div>
              <h3 className="mt-5 text-base font-semibold text-[var(--color-foreground)]">
                {title}
              </h3>
              <p className="mt-2.5 text-[15px] leading-relaxed text-[var(--color-muted)]">
                {body}
              </p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
