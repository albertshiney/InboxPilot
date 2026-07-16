import Link from "next/link";
import Reveal from "./Reveal";

export default function CtaBand() {
  return (
    <section className="bg-[var(--color-ink)]">
      <div className="relative mx-auto max-w-6xl overflow-hidden px-5 py-20 text-center sm:px-8 sm:py-24">
        {/* Faint flight path echo from the hero, landing this time. */}
        <svg
          aria-hidden="true"
          viewBox="0 0 1200 300"
          fill="none"
          className="pointer-events-none absolute inset-0 h-full w-full"
          preserveAspectRatio="xMidYMid slice"
        >
          <path
            d="M-40 280 C 300 260, 620 200, 820 130 S 1080 40, 1240 10"
            stroke="#6366F1"
            strokeOpacity="0.35"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeDasharray="1 8"
          />
        </svg>

        <Reveal>
          <h2 className="font-display relative text-balance text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Put your support inbox on autopilot
          </h2>
          <p className="relative mx-auto mt-4 max-w-xl text-pretty text-lg text-slate-400">
            Connect Gmail, upload your docs, and watch the first drafts land in
            minutes.
          </p>
          <div className="relative mt-9">
            <Link
              href="/signup"
              className="inline-block rounded-[var(--radius-md)] bg-white px-8 py-3.5 text-base font-medium text-[var(--color-ink)] shadow-lg transition-all hover:-translate-y-0.5 hover:bg-slate-100"
            >
              Start your 7-day free trial
            </Link>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
