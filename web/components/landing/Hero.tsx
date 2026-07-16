import Link from "next/link";
import InboxQueueMock from "./InboxQueueMock";

// The flight path: drawn on load behind the headline, ending in the
// brand's paper plane. This is the page's one orchestrated moment.
function FlightPath() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-x-0 top-0 flex justify-center overflow-hidden"
    >
      <svg
        viewBox="0 0 1200 420"
        className="h-[420px] w-[1200px] max-w-none"
        fill="none"
      >
        <defs>
          <linearGradient id="hero-path" x1="0" y1="420" x2="1200" y2="0">
            <stop offset="0%" stopColor="#4F46E5" stopOpacity="0" />
            <stop offset="55%" stopColor="#4F46E5" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#6366F1" stopOpacity="0.9" />
          </linearGradient>
          <radialGradient id="hero-glow" cx="50%" cy="0%" r="80%">
            <stop offset="0%" stopColor="#EEF2FF" />
            <stop offset="100%" stopColor="#EEF2FF" stopOpacity="0" />
          </radialGradient>
        </defs>

        <rect width="1200" height="420" fill="url(#hero-glow)" opacity="0.8" />

        <path
          d="M-40 400 C 260 380, 520 330, 720 240 S 1020 90, 1140 48"
          stroke="url(#hero-path)"
          strokeWidth="2"
          strokeLinecap="round"
          pathLength={1}
          strokeDasharray="1"
          strokeDashoffset="1"
          style={{
            animation: "draw-path 1.6s cubic-bezier(0.65, 0, 0.35, 1) 0.3s forwards",
          }}
        />

        <g
          className="anim-fade anim-delay-5"
          style={{ transformOrigin: "1146px 44px" }}
        >
          <g style={{ animation: "plane-drift 5s ease-in-out 2s infinite" }}>
            <path
              d="M1160 30 L1136 66 L1141 48 L1128 42 Z"
              fill="#4F46E5"
              transform="rotate(8 1146 44)"
            />
          </g>
        </g>
      </svg>
    </div>
  );
}

export default function Hero() {
  return (
    <section className="relative mx-auto max-w-6xl px-5 pb-20 pt-20 sm:px-8 sm:pb-28 sm:pt-28">
      <FlightPath />

      <div className="relative mx-auto max-w-3xl text-center">
        <p className="anim-rise inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-white px-4 py-1.5 text-sm font-medium text-[var(--color-muted)] shadow-sm">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          Grounded AI replies, reviewed or auto-sent
        </p>

        <h1 className="anim-rise anim-delay-1 font-display mt-6 text-balance text-[2.6rem] font-semibold leading-[1.08] tracking-tight text-[var(--color-foreground)] sm:text-6xl">
          Answer support emails before you open your inbox
        </h1>

        <p className="anim-rise anim-delay-2 mx-auto mt-6 max-w-xl text-pretty text-lg leading-relaxed text-[var(--color-muted)]">
          InboxPilot drafts a grounded reply to every incoming support email
          from your own docs — approve with one click, or let guardrailed
          Autopilot send the confident ones.
        </p>

        <div className="anim-rise anim-delay-3 mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            href="/signup"
            className="w-full rounded-[var(--radius-md)] bg-[var(--color-accent)] px-7 py-3.5 text-base font-medium text-white shadow-[0_1px_2px_rgb(79_70_229_/_0.4),0_8px_24px_-8px_rgb(79_70_229_/_0.5)] transition-all hover:-translate-y-0.5 hover:bg-[var(--color-accent-hover)] sm:w-auto"
          >
            Start free trial
          </Link>
          <a
            href="#how-it-works"
            className="w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white px-7 py-3.5 text-base font-medium text-[var(--color-foreground)] shadow-sm transition-colors hover:border-[var(--color-border-strong)] hover:bg-[var(--color-app-bg)] sm:w-auto"
          >
            See how it works
          </a>
        </div>

        <p className="anim-rise anim-delay-4 mt-4 text-sm text-[var(--color-faint)]">
          7-day free trial · card required · $49/mo after
        </p>
      </div>

      <div className="anim-scale anim-delay-4 mx-auto mt-16 max-w-4xl sm:mt-20">
        <InboxQueueMock />
      </div>
    </section>
  );
}
