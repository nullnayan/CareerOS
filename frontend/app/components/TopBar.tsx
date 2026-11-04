"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "../lib/utils";
import { useWorkspace } from "../context/WorkspaceContext";

/** Frequently used workspace routes. */
const PRIMARY = [
  { href: "/", label: "Overview" },
  { href: "/jobs", label: "Jobs" },
  { href: "/master", label: "Master Resume" },
  { href: "/ats", label: "ATS" },
  { href: "/tailor", label: "Tailor" },
];

/** Everything else lives one click away. */
const OVERFLOW = [
  { href: "/applications", label: "Applications" },
  { href: "/automation", label: "Automation" },
  { href: "/autofill", label: "Browser autofill" },
  { href: "/resume", label: "Resumes" },
  { href: "/settings", label: "Settings" },
  { href: "/builder", label: "Builder" },
  { href: "/skills", label: "Skills" },
  { href: "/chat", label: "Chat" },
  { href: "/github", label: "GitHub" },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

/** Click-outside + Escape, shared by both menus. */
function useDismiss<T extends HTMLElement>(open: boolean, close: () => void) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);
  return ref;
}

const menuPanel =
  "absolute right-0 top-[calc(100%+6px)] z-50 min-w-[180px] rounded-lg border border-rule bg-surface py-1 shadow-md";
const menuItem =
  "block w-full px-3 py-1.5 text-left text-sm text-ink-secondary transition-colors duration-100 hover:bg-sunken hover:text-ink";

export default function TopBar() {
  const pathname = usePathname();
  const { user } = useWorkspace();

  const [moreOpen, setMoreOpen] = useState(false);
  const [acctOpen, setAcctOpen] = useState(false);

  const moreRef = useDismiss<HTMLDivElement>(moreOpen, () => setMoreOpen(false));
  const acctRef = useDismiss<HTMLDivElement>(acctOpen, () => setAcctOpen(false));

  // Route change closes whatever was open.
  useEffect(() => {
    setMoreOpen(false);
    setAcctOpen(false);
  }, [pathname]);

  const email = user?.email ?? "";
  const initials = email.slice(0, 2).toUpperCase() || "··";
  const overflowActive = OVERFLOW.some((i) => isActive(pathname, i.href));

  return (
    <header className="sticky top-0 z-40 border-b border-rule bg-paper">
      <div className="mx-auto flex h-14 max-w-[1100px] items-center gap-6 px-6">
        <Link
          href="/"
          className="font-serif text-lg tracking-tight text-ink no-underline"
        >
          CareerOS
        </Link>

        <nav className="flex items-center gap-1" aria-label="Primary">
          {PRIMARY.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative hidden rounded px-2.5 py-1.5 text-sm transition-colors duration-100 md:block",
                  active
                    ? "text-accent"
                    : "text-ink-secondary hover:text-ink"
                )}
              >
                {item.label}
                {active && (
                  <span className="absolute inset-x-2.5 -bottom-[9px] h-[2px] bg-accent" />
                )}
              </Link>
            );
          })}

          <div className="relative" ref={moreRef}>
            <button
              type="button"
              onClick={() => setMoreOpen((v) => !v)}
              aria-expanded={moreOpen}
              aria-haspopup="menu"
              className={cn(
                "relative flex items-center gap-1 rounded px-2.5 py-1.5 text-sm transition-colors duration-100",
                overflowActive
                  ? "text-accent"
                  : "text-ink-secondary hover:text-ink"
              )}
            >
              More
              <ChevronDown className="h-3.5 w-3.5" />
              {overflowActive && (
                <span className="absolute inset-x-2.5 -bottom-[9px] h-[2px] bg-accent" />
              )}
            </button>

            {moreOpen && (
              <div role="menu" className={cn(menuPanel, "left-0 right-auto")}>
                {[...PRIMARY, ...OVERFLOW].map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    role="menuitem"
                    className={cn(
                      menuItem,
                      PRIMARY.some(p => p.href === item.href) && "md:hidden",
                      isActive(pathname, item.href) && "text-accent"
                    )}
                  >
                    {item.label}
                  </Link>
                ))}
              </div>
            )}
          </div>
        </nav>

        <div className="relative ml-auto" ref={acctRef}>
          <button
            type="button"
            onClick={() => setAcctOpen((v) => !v)}
            aria-expanded={acctOpen}
            aria-haspopup="menu"
            aria-label="Workspace menu"
            className="flex h-8 w-8 items-center justify-center rounded-full border border-rule-strong bg-surface text-xs font-medium text-ink-secondary transition-colors duration-100 hover:border-ink-tertiary hover:text-ink"
          >
            {initials}
          </button>

          {acctOpen && (
            <div role="menu" className={menuPanel}>
              {email && (
                <p className="truncate border-b border-rule px-3 pb-2 pt-1 text-xs text-ink-tertiary">
                  {email}
                </p>
              )}
              <Link href="/settings" role="menuitem" className={menuItem}>Personal workspace settings</Link>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
