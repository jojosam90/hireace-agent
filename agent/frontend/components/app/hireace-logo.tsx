'use client';

import { type OnlineStatus, useOnlineStatus } from '@/hooks/useOnlineStatus';
import { type StringKey, useUiLanguage } from '@/lib/i18n';

const STATUS: Record<OnlineStatus, { label: StringKey; color: string }> = {
  online: { label: 'statusOnline', color: 'bg-emerald-500' },
  connecting: { label: 'statusConnecting', color: 'bg-amber-400' },
  offline: { label: 'statusOffline', color: 'bg-zinc-400' },
  unknown: { label: 'statusUnknown', color: 'bg-zinc-300' },
};

/**
 * The HireAce logo, top left of every screen: the mark with a dot showing whether
 * HireAce is there (green: online), plus the name on wider screens (in the narrow
 * panel the Full view / My PC button sits next to the mark).
 */
export function HireAceLogo() {
  const { t } = useUiLanguage();
  const status = STATUS[useOnlineStatus()];

  return (
    <div
      className="fixed top-4 left-4 z-50 flex items-center gap-2"
      role="img"
      aria-label={`HireAce: ${t(status.label)}`}
      title={t(status.label)}
    >
      <span className="relative">
        <svg
          viewBox="0 0 64 64"
          className="size-8 shadow-xs"
          style={{ borderRadius: 7 }}
          aria-hidden
        >
          <rect width="64" height="64" rx="14" fill="#0f172a" />
          <circle cx="32" cy="15" r="5.5" fill="#2f6bff" />
          <path
            d="M18 52 32 25 46 52M24.5 42h15"
            fill="none"
            stroke="#fff"
            strokeWidth="6"
            strokeLinejoin="round"
          />
        </svg>
        <span
          className={`border-background absolute -right-1 -bottom-1 size-3.5 rounded-full border-2 ${status.color}`}
          aria-hidden
        />
      </span>
      <span className="hidden text-lg font-bold tracking-tight md:inline" aria-hidden>
        <span className="text-foreground">Hire</span>
        <span style={{ color: '#2f6bff' }}>Ace</span>
      </span>
    </div>
  );
}
