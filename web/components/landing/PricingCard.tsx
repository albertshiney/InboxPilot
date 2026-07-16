import Link from "next/link";
import { Check } from "lucide-react";
import Reveal from "./Reveal";

const FEATURES = [
  "500 emails/month",
  "Unlimited docs in your knowledge base",
  "AI-drafted replies with confidence scoring",
  "Guardrailed Autopilot",
  "Every draft shows its sources and confidence",
];

export default function PricingCard() {
  return (
    <section id="pricing" className="border-t border-[var(--color-border)] bg-white">
      <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 sm:py-28">
        <Reveal>
          <div className="text-center">
            <p className="text-sm font-semibold uppercase tracking-[0.14em] text-[var(--color-accent)]">
              Pricing
            </p>
            <h2 className="font-display mt-3 text-balance text-3xl font-semibold tracking-tight text-[var(--color-foreground)] sm:text-4xl">
              One plan. Everything included.
            </h2>
          </div>
        </Reveal>

        <Reveal delay={120}>
          <div className="mx-auto mt-12 max-w-md overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-raised)]">
            <div className="h-1.5 bg-gradient-to-r from-[#4338CA] via-[#4F46E5] to-[#6366F1]" />
            <div className="p-8 sm:p-10">
              <div className="text-center">
                <p className="flex items-baseline justify-center gap-1.5">
                  <span className="readout text-5xl font-semibold tracking-tight text-[var(--color-foreground)]">
                    $49
                  </span>
                  <span className="text-base text-[var(--color-muted)]">/month</span>
                </p>
                <p className="mt-2 text-[15px] text-[var(--color-muted)]">
                  500 emails/month · 7-day free trial
                </p>
              </div>

              <ul className="mt-8 flex flex-col gap-3.5">
                {FEATURES.map((feature) => (
                  <li
                    key={feature}
                    className="flex items-start gap-3 text-[15px] text-[var(--color-foreground)]"
                  >
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-accent-soft)]">
                      <Check className="h-3 w-3 text-[var(--color-accent)]" strokeWidth={3} />
                    </span>
                    {feature}
                  </li>
                ))}
              </ul>

              <Link
                href="/signup"
                className="mt-9 block w-full rounded-[var(--radius-md)] bg-[var(--color-accent)] px-6 py-3.5 text-center text-base font-medium text-white shadow-sm transition-all hover:-translate-y-0.5 hover:bg-[var(--color-accent-hover)]"
              >
                Start free trial
              </Link>
              <p className="mt-4 text-center text-sm text-[var(--color-faint)]">
                Card required to start · cancel anytime
              </p>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
