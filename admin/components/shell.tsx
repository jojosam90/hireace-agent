'use client';

import { Activity, Gauge, LayoutDashboard, LogOut, Monitor, PackageCheck } from 'lucide-react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

const NAV = [
  { href: '/', label: 'Overview', icon: LayoutDashboard },
  { href: '/workstations', label: 'Workstations', icon: Monitor },
  { href: '/usage', label: 'Usage', icon: Gauge },
  { href: '/releases', label: 'Releases', icon: PackageCheck },
  { href: '/activity', label: 'Activity', icon: Activity },
];

export function Logo() {
  return (
    <div className="flex items-center gap-3">
      <span className="flex size-12 items-center justify-center rounded-xl border border-white/25 bg-white/15 p-1.5">
        <Image src="/logo.png" alt="" width={36} height={36} className="rounded-md" priority />
      </span>
      <span>
        <span className="block text-2xl leading-tight font-extrabold">HireAce</span>
        <span className="block text-xs font-semibold tracking-wide text-white/85 uppercase">Admin portal</span>
      </span>
    </div>
  );
}

async function signOut() {
  await fetch('/api/auth/logout', { method: 'POST' });
  window.location.href = '/login';
}

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const isCurrent = (href: string) => (href === '/' ? path === '/' : path.startsWith(href));

  return (
    <div className="min-h-dvh lg:pl-64">
      {/* Large screens: a side bar */}
      <aside className="brand-gradient fixed inset-y-0 left-0 hidden w-64 flex-col p-5 text-white lg:flex">
        <Logo />
        <nav className="mt-9 flex-1 space-y-1.5" aria-label="Main">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              aria-current={isCurrent(href) ? 'page' : undefined}
              className={`flex items-center gap-3 rounded-xl px-3.5 py-2.5 font-semibold transition-colors ${
                isCurrent(href) ? 'text-brand-700 bg-white shadow-sm' : 'text-white/90 hover:bg-white/15'
              }`}
            >
              <Icon className="size-5" aria-hidden />
              {label}
            </Link>
          ))}
        </nav>
        <button
          type="button"
          onClick={signOut}
          className="flex items-center gap-3 rounded-xl px-3.5 py-2.5 font-semibold text-white/90 transition-colors hover:bg-white/15"
        >
          <LogOut className="size-5" aria-hidden />
          Sign out
        </button>
      </aside>

      {/* Phones and tablets: a top band and a bottom bar */}
      <header className="brand-gradient flex items-center justify-between px-4 py-3 text-white lg:hidden">
        <Logo />
        <button type="button" onClick={signOut} aria-label="Sign out" className="rounded-lg p-2 hover:bg-white/15">
          <LogOut className="size-5" aria-hidden />
        </button>
      </header>

      <main className="mx-auto max-w-6xl px-4 pt-5 pb-24 sm:px-6 lg:px-8 lg:py-8">{children}</main>

      <nav
        aria-label="Main"
        className="border-line fixed inset-x-0 bottom-0 z-20 grid grid-cols-5 border-t bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
      >
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            aria-current={isCurrent(href) ? 'page' : undefined}
            className={`flex flex-col items-center gap-0.5 py-2 text-[11px] font-bold ${
              isCurrent(href) ? 'text-brand-700' : 'text-muted'
            }`}
          >
            <Icon className="size-5" aria-hidden />
            {label === 'Workstations' ? 'PCs' : label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
