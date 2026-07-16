"use client";

import { useSyncExternalStore } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Inbox,
  BookOpen,
  SlidersHorizontal,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import Logo, { LogoMark } from "@/components/Logo";

export const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/inbox", label: "Inbox", icon: Inbox },
  { href: "/ai-behavior", label: "AI behavior", icon: SlidersHorizontal },
  { href: "/knowledge", label: "Knowledge", icon: BookOpen },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

// Desktop sidebar pins Settings to the bottom; MobileNav renders the full
// NAV_ITEMS list in order.
const SETTINGS_ITEM = NAV_ITEMS[NAV_ITEMS.length - 1];
const MAIN_ITEMS = NAV_ITEMS.filter((item) => item !== SETTINGS_ITEM);

const STORAGE_KEY = "inboxpilot:sidebar-collapsed";
const COLLAPSE_EVENT = "inboxpilot:sidebar-collapsed-change";

function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener(COLLAPSE_EVENT, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(COLLAPSE_EVENT, callback);
  };
}

function getSnapshot() {
  return window.localStorage.getItem(STORAGE_KEY) === "true";
}

function getServerSnapshot() {
  return false;
}

function setCollapsed(next: boolean) {
  window.localStorage.setItem(STORAGE_KEY, String(next));
  window.dispatchEvent(new Event(COLLAPSE_EVENT));
}

function NavLink({
  item,
  pathname,
  collapsed,
}: {
  item: (typeof NAV_ITEMS)[number];
  pathname: string | null;
  collapsed: boolean;
}) {
  const { href, label, icon: Icon } = item;
  const active = pathname === href || pathname?.startsWith(`${href}/`);
  return (
    <Link
      href={href}
      title={collapsed ? label : undefined}
      className={`flex items-center gap-3 rounded-[var(--radius-sm)] px-3 py-2.5 text-[15px] transition-colors ${
        collapsed ? "justify-center" : ""
      } ${
        active
          ? "bg-[var(--color-accent-soft)] font-medium text-[var(--color-accent)]"
          : "text-[var(--color-muted)] hover:bg-[var(--color-app-bg)] hover:text-[var(--color-foreground)]"
      }`}
    >
      <Icon size={19} className="shrink-0" strokeWidth={active ? 2.2 : 2} />
      {!collapsed && <span className="truncate">{label}</span>}
    </Link>
  );
}

export default function Sidebar() {
  const pathname = usePathname();
  const collapsed = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot,
  );

  return (
    <aside
      className="sticky top-0 hidden h-screen flex-col border-r border-[var(--color-border)] bg-white transition-[width] duration-200 ease-in-out lg:flex"
      style={{ width: collapsed ? 68 : 248 }}
    >
      <div className={`flex items-center py-5 ${collapsed ? "justify-center px-0" : "px-5"}`}>
        <Link href="/dashboard" aria-label="InboxPilot dashboard">
          {collapsed ? <LogoMark size={30} /> : <Logo size={30} />}
        </Link>
      </div>

      <nav className="flex flex-1 flex-col gap-1 px-3 pt-2">
        {MAIN_ITEMS.map((item) => (
          <NavLink key={item.href} item={item} pathname={pathname} collapsed={collapsed} />
        ))}
      </nav>

      <div className="flex flex-col gap-1 border-t border-[var(--color-border)] p-3">
        <NavLink item={SETTINGS_ITEM} pathname={pathname} collapsed={collapsed} />
        <button
          type="button"
          onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={`flex w-full items-center gap-3 rounded-[var(--radius-sm)] px-3 py-2.5 text-[15px] text-[var(--color-muted)] transition-colors hover:bg-[var(--color-app-bg)] hover:text-[var(--color-foreground)] ${
            collapsed ? "justify-center" : ""
          }`}
        >
          {collapsed ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
