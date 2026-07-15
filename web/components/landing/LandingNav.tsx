import Link from "next/link";

export default function LandingNav() {
  return (
    <header className="border-b border-[var(--color-border)] bg-[var(--color-card-bg)]">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <span className="text-base font-semibold tracking-tight text-[var(--color-foreground)]">
          InboxPilot
        </span>

        <nav className="flex items-center gap-4 sm:gap-6">
          <Link
            href="/login"
            className="text-sm font-medium text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
          >
            Login
          </Link>
          <Link
            href="/signup"
            className="rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-3.5 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
          >
            Start free trial
          </Link>
        </nav>
      </div>
    </header>
  );
}
