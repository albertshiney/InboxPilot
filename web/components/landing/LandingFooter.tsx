import Link from "next/link";
import Logo from "@/components/Logo";

export default function LandingFooter() {
  return (
    <footer className="border-t border-[var(--color-border)] bg-white">
      <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8">
        <div className="flex flex-col items-start justify-between gap-8 sm:flex-row sm:items-center">
          <div>
            <Logo size={26} />
            <p className="mt-3 max-w-xs text-sm leading-relaxed text-[var(--color-muted)]">
              AI-drafted replies for your support inbox, grounded in your own
              docs.
            </p>
          </div>
          <nav className="flex flex-wrap items-center gap-x-6 gap-y-3 text-sm font-medium text-[var(--color-muted)]">
            <a href="#how-it-works" className="transition-colors hover:text-[var(--color-foreground)]">
              How it works
            </a>
            <a href="#pricing" className="transition-colors hover:text-[var(--color-foreground)]">
              Pricing
            </a>
            <Link href="/login" className="transition-colors hover:text-[var(--color-foreground)]">
              Log in
            </Link>
            <Link href="/signup" className="transition-colors hover:text-[var(--color-foreground)]">
              Start free trial
            </Link>
          </nav>
        </div>
        <p className="mt-10 border-t border-[var(--color-border)] pt-6 text-sm text-[var(--color-faint)]">
          &copy; {new Date().getFullYear()} InboxPilot. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
