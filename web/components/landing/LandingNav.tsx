import Link from "next/link";
import Logo from "@/components/Logo";

export default function LandingNav() {
  return (
    <header className="sticky top-0 z-40 border-b border-[var(--color-border)]/80 bg-white/80 backdrop-blur-md">
      <div className="mx-auto flex h-[72px] max-w-6xl items-center justify-between px-5 sm:px-8">
        <Link href="/" aria-label="InboxPilot home">
          <Logo />
        </Link>

        <nav className="hidden items-center gap-8 text-[15px] font-medium text-[var(--color-muted)] md:flex">
          <a href="#how-it-works" className="transition-colors hover:text-[var(--color-foreground)]">
            How it works
          </a>
          <a href="#features" className="transition-colors hover:text-[var(--color-foreground)]">
            Features
          </a>
          <a href="#pricing" className="transition-colors hover:text-[var(--color-foreground)]">
            Pricing
          </a>
        </nav>

        <nav className="flex items-center gap-3 sm:gap-4">
          <Link
            href="/login"
            className="rounded-[var(--radius-sm)] px-3 py-2 text-[15px] font-medium text-[var(--color-muted)] transition-colors hover:text-[var(--color-foreground)]"
          >
            Log in
          </Link>
          <Link
            href="/signup"
            className="rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-4 py-2.5 text-[15px] font-medium text-white shadow-sm transition-colors hover:bg-[var(--color-accent-hover)]"
          >
            Start free trial
          </Link>
        </nav>
      </div>
    </header>
  );
}
