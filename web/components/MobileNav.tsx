"use client";

// Mobile app navigation: a sticky top bar with the brand mark and a
// hamburger that opens a slide-over drawer. Hidden at lg and up, where
// the Sidebar takes over.

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";
import Logo from "@/components/Logo";
import { NAV_ITEMS } from "@/components/Sidebar";

export default function MobileNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // Close the drawer on navigation — adjusted during render per React's
  // guidance rather than in an effect. Body scroll locks while it's open.
  const [seenPathname, setSeenPathname] = useState(pathname);
  if (pathname !== seenPathname) {
    setSeenPathname(pathname);
    setOpen(false);
  }

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      <header className="sticky top-0 z-40 flex h-16 items-center justify-between border-b border-[var(--color-border)] bg-white/90 px-4 backdrop-blur-md lg:hidden">
        <Link href="/dashboard" aria-label="InboxPilot dashboard">
          <Logo size={28} />
        </Link>
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open navigation"
          className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-muted)] hover:bg-[var(--color-app-bg)] hover:text-[var(--color-foreground)]"
        >
          <Menu size={22} />
        </button>
      </header>

      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-[var(--color-ink)]/40 backdrop-blur-sm"
          />
          <div className="anim-rise absolute inset-y-0 right-0 flex w-[300px] max-w-[85vw] flex-col bg-white shadow-[var(--shadow-overlay)]">
            <div className="flex h-16 items-center justify-between border-b border-[var(--color-border)] px-5">
              <Logo size={28} />
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close navigation"
                className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-muted)] hover:bg-[var(--color-app-bg)]"
              >
                <X size={20} />
              </button>
            </div>
            <nav className="flex flex-col gap-1 p-4">
              {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
                const active =
                  pathname === href || pathname?.startsWith(`${href}/`);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={`flex items-center gap-3.5 rounded-[var(--radius-md)] px-4 py-3.5 text-base transition-colors ${
                      active
                        ? "bg-[var(--color-accent-soft)] font-medium text-[var(--color-accent)]"
                        : "text-[var(--color-muted)] hover:bg-[var(--color-app-bg)] hover:text-[var(--color-foreground)]"
                    }`}
                  >
                    <Icon size={21} strokeWidth={active ? 2.2 : 2} />
                    {label}
                  </Link>
                );
              })}
            </nav>
          </div>
        </div>
      )}
    </>
  );
}
