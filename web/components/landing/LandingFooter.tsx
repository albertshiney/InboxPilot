import Link from "next/link";

export default function LandingFooter() {
  return (
    <footer className="border-t border-[var(--color-border)]">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-4 py-8 text-sm text-[var(--color-muted)] sm:flex-row sm:px-6">
        <span>&copy; {new Date().getFullYear()} InboxPilot</span>
        <div className="flex items-center gap-5">
          <Link href="/login" className="hover:text-[var(--color-foreground)]">
            Login
          </Link>
          <Link href="/signup" className="hover:text-[var(--color-foreground)]">
            Start free trial
          </Link>
        </div>
      </div>
    </footer>
  );
}
