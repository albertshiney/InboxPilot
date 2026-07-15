import Link from "next/link";
import InboxQueueMock from "./InboxQueueMock";

export default function Hero() {
  return (
    <section className="mx-auto max-w-6xl px-4 pb-16 pt-14 sm:px-6 sm:pb-24 sm:pt-20">
      <div className="mx-auto max-w-2xl text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-[var(--color-foreground)] sm:text-5xl sm:leading-[1.1]">
          Answer support emails before you open your inbox
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-base text-[var(--color-muted)] sm:text-lg">
          InboxPilot drafts a grounded reply to every incoming support email
          from your own docs — approve with one click, or let guardrailed
          Autopilot send the confident ones.
        </p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            href="/signup"
            className="w-full rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-5 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 sm:w-auto"
          >
            Start free trial
          </Link>
          <Link
            href="/login"
            className="w-full rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-card-bg)] px-5 py-2.5 text-sm font-medium text-[var(--color-foreground)] transition-colors hover:bg-[var(--color-app-bg)] sm:w-auto"
          >
            Login
          </Link>
        </div>
        <p className="mt-3 text-xs text-[var(--color-muted)]">
          7-day free trial · card required · $49/mo after
        </p>
      </div>

      <div className="mx-auto mt-14 max-w-3xl">
        <InboxQueueMock />
      </div>
    </section>
  );
}
