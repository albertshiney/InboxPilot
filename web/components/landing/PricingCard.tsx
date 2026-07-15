import Link from "next/link";
import { Check } from "lucide-react";

const FEATURES = [
  "500 emails/month",
  "Unlimited docs in your knowledge base",
  "AI-drafted replies with confidence scoring",
  "Guardrailed Autopilot",
  "One review queue for your whole team",
];

export default function PricingCard() {
  return (
    <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
      <div className="mx-auto max-w-md rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)] p-8 shadow-sm">
        <div className="text-center">
          <p className="text-sm font-medium text-[var(--color-accent)]">
            Simple pricing
          </p>
          <p className="mt-2 flex items-baseline justify-center gap-1">
            <span className="text-4xl font-semibold tracking-tight text-[var(--color-foreground)]">
              $49
            </span>
            <span className="text-sm text-[var(--color-muted)]">/mo</span>
          </p>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            500 emails/month · 7-day free trial
          </p>
        </div>

        <ul className="mt-6 flex flex-col gap-3">
          {FEATURES.map((feature) => (
            <li
              key={feature}
              className="flex items-start gap-2.5 text-sm text-[var(--color-foreground)]"
            >
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-accent)]" />
              {feature}
            </li>
          ))}
        </ul>

        <Link
          href="/signup"
          className="mt-8 block w-full rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-5 py-2.5 text-center text-sm font-medium text-white transition-opacity hover:opacity-90"
        >
          Start free trial
        </Link>
        <p className="mt-3 text-center text-xs text-[var(--color-muted)]">
          Card required to start · cancel anytime
        </p>
      </div>
    </section>
  );
}
