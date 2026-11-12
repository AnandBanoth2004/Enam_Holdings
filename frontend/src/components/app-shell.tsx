"use client";

import {
  Activity,
  Command,
  Compass,
  FileSearch,
  Search,
  Settings2,
  Sparkles,
  UsersRound,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { FormEvent, ReactNode } from "react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { ApiStatus } from "@/components/api-status";

const primaryNavigation = [
  { href: "/", label: "Command centre", mobileLabel: "Today", icon: Command },
  { href: "/push", label: "Push intelligence", mobileLabel: "Push", icon: Activity },
  { href: "/research", label: "Company research", mobileLabel: "Research", icon: FileSearch },
  { href: "/network", label: "Network intelligence", mobileLabel: "Network", icon: UsersRound },
  { href: "/copilot", label: "Research copilot", mobileLabel: "Ask", icon: Sparkles },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ticker, setTicker] = useState("");

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = ticker.trim();
    if (value) router.push(`/research?ticker=${encodeURIComponent(value)}`);
  }

  return (
    <div className="min-h-screen bg-canvas">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[232px] flex-col border-r border-line bg-surface lg:flex">
        <Link className="flex h-[68px] items-center gap-3 border-b border-line px-5" href="/">
          <span className="flex size-8 items-center justify-center rounded-md bg-brand text-[13px] font-bold tracking-wide text-white">F</span>
          <span className="leading-tight">
            <span className="block text-[15px] font-semibold tracking-[-0.03em] text-ink">FINN</span>
            <span className="mt-0.5 block text-[10px] font-medium text-ink-muted">Investment intelligence</span>
          </span>
        </Link>
        <div className="px-3 pt-5">
          <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-muted">Workspace</p>
          <nav aria-label="Primary navigation" className="space-y-1">
            {primaryNavigation.map(({ href, label, icon: Icon }) => {
              const active = isActive(pathname, href);
              return (
                <Link
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex min-h-10 items-center gap-3 rounded-md px-3 text-[13px] font-medium transition-colors",
                    active
                      ? "bg-brand-tint text-brand"
                      : "text-ink-secondary hover:bg-surface-muted hover:text-ink",
                  )}
                  href={href}
                  key={href}
                >
                  <Icon aria-hidden="true" size={17} strokeWidth={1.8} />
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>
        <div className="mt-auto border-t border-line p-3">
          <Link
            aria-current={pathname === "/settings" ? "page" : undefined}
            className={cn(
              "flex min-h-10 items-center gap-3 rounded-md px-3 text-[13px] font-medium",
              pathname === "/settings"
                ? "bg-brand-tint text-brand"
                : "text-ink-secondary hover:bg-surface-muted hover:text-ink",
            )}
            href="/settings"
          >
            <Settings2 aria-hidden="true" size={17} strokeWidth={1.8} />
            Settings
          </Link>
          <div className="mt-3 flex items-center gap-3 rounded-md bg-surface-muted p-3">
            <span className="flex size-8 items-center justify-center rounded-full bg-white text-xs font-semibold text-brand">DM</span>
            <span className="min-w-0">
              <span className="block truncate text-xs font-semibold text-ink">Demo workspace</span>
              <span className="mt-0.5 block text-[10px] text-ink-muted">Synthetic data</span>
            </span>
          </div>
        </div>
      </aside>

      <div className="lg:pl-[232px]">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-line bg-surface/95 px-4 backdrop-blur sm:px-6 lg:h-[68px] lg:px-8">
          <div className="flex items-center gap-2 lg:hidden">
            <span className="flex size-7 items-center justify-center rounded bg-brand text-xs font-bold text-white">F</span>
            <span className="text-sm font-semibold tracking-tight text-ink">FINN</span>
          </div>
          <form
            className="hidden max-w-[420px] flex-1 items-center gap-2 rounded-md border border-line bg-surface px-3 lg:flex"
            onSubmit={handleSearch}
            role="search"
          >
            <Search aria-hidden="true" className="shrink-0 text-ink-muted" size={16} />
            <input
              aria-label="Search a company or ticker"
              className="h-9 min-w-0 flex-1 bg-transparent text-xs text-ink outline-none placeholder:text-ink-muted"
              onChange={(event) => setTicker(event.target.value)}
              placeholder="Search any supported company or ticker"
              value={ticker}
            />
            <kbd className="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-muted">↵</kbd>
          </form>
          <div className="ml-auto flex items-center gap-3">
            <div className="hidden items-center gap-2 sm:flex">
              <ApiStatus />
            </div>
            <Link
              aria-label="Open settings"
              className="flex size-10 items-center justify-center rounded-md text-ink-secondary hover:bg-surface-muted hover:text-ink lg:hidden"
              href="/settings"
            >
              <Settings2 aria-hidden="true" size={18} />
            </Link>
            <Link
              className="hidden items-center gap-2 rounded-md border border-line px-3 py-2 text-xs font-medium text-ink-secondary hover:bg-surface-muted sm:inline-flex"
              href="/settings"
            >
              <Compass aria-hidden="true" size={15} />
              Demo workspace
            </Link>
          </div>
        </header>

        <main className="min-h-[calc(100vh-56px)] pb-20 lg:min-h-[calc(100vh-68px)] lg:pb-0">
          {children}
        </main>
      </div>

      <nav
        aria-label="Mobile navigation"
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-line bg-surface/95 px-1 pb-[env(safe-area-inset-bottom)] pt-1 backdrop-blur lg:hidden"
      >
        {primaryNavigation.map(({ href, mobileLabel, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Link
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex min-h-[52px] flex-col items-center justify-center gap-1 rounded-md text-[10px] font-medium",
                active ? "text-brand" : "text-ink-muted",
              )}
              href={href}
              key={href}
            >
              <Icon aria-hidden="true" size={18} strokeWidth={active ? 2 : 1.7} />
              <span>{mobileLabel}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
