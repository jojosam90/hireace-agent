'use client';

import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  CircleOff,
  LoaderCircle,
  Power,
  RefreshCw,
  WifiOff,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useRef, type ComponentProps, type ReactNode } from 'react';
import type { DeviceView } from '@/lib/types';

/**
 * With fill, the page is exactly one screen tall (less the header, bottom bar and
 * spacing in shell.tsx) and a long list scrolls inside its own card.
 */
export function Page({ title, intro, actions, fill, children }: { title: string; intro?: string; actions?: ReactNode; fill?: boolean; children: ReactNode }) {
  return (
    <div className={fill ? 'flex h-[calc(100dvh-188px)] min-h-[420px] flex-col lg:h-[calc(100dvh-4rem)]' : undefined}>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">{title}</h1>
          {intro && <p className="text-muted mt-1 max-w-2xl">{intro}</p>}
        </div>
        {actions}
      </div>
      {children}
    </div>
  );
}

export function Card({ className = '', children, ...rest }: ComponentProps<'section'>) {
  return (
    <section className={`border-line rounded-2xl border bg-white p-4 shadow-sm sm:p-5 ${className}`} {...rest}>
      {children}
    </section>
  );
}

export function CardTitle({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="mb-3">
      <h2 className="text-lg font-extrabold">{children}</h2>
      {hint && <p className="text-muted text-sm">{hint}</p>}
    </div>
  );
}

type Tone = 'good' | 'warn' | 'bad' | 'off' | 'brand';

const TONES: Record<Tone, string> = {
  good: 'bg-emerald-50 text-emerald-800',
  warn: 'bg-amber-50 text-amber-900',
  bad: 'bg-red-50 text-red-800',
  off: 'bg-zinc-100 text-zinc-700',
  brand: 'bg-brand-50 text-brand-700',
};

export function Badge({ tone, icon: Icon, spin, children }: { tone: Tone; icon?: LucideIcon; spin?: boolean; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold whitespace-nowrap ${TONES[tone]}`}>
      {Icon && <Icon className={`size-3.5 ${spin ? 'animate-spin' : ''}`} aria-hidden />}
      {children}
    </span>
  );
}

const STATES: Record<DeviceView['state'], { tone: Tone; icon: LucideIcon; label: string; spin?: boolean }> = {
  up: { tone: 'good', icon: CheckCircle2, label: 'Online · HireAce up' },
  partial: { tone: 'warn', icon: AlertTriangle, label: 'Online · Partly up' },
  down: { tone: 'off', icon: CircleDashed, label: 'Online · HireAce down' },
  offline: { tone: 'bad', icon: WifiOff, label: 'Offline' },
  updating: { tone: 'brand', icon: LoaderCircle, label: 'Updating', spin: true },
  deactivated: { tone: 'off', icon: CircleOff, label: 'Deactivated' },
};

export function StateBadge({ state }: { state: DeviceView['state'] }) {
  const { tone, icon, label, spin } = STATES[state];
  return (
    <Badge tone={tone} icon={icon} spin={spin}>
      {label}
    </Badge>
  );
}

export function OrderNote({ device }: { device: DeviceView }) {
  const order = device.order;
  if (!order) return null;
  const what = order.type === 'update' ? `Update to ${order.version ?? 'latest'}` : 'Restart';
  const text =
    order.status === 'pending'
      ? device.inCall
        ? `${what} waits for the call to end`
        : `${what} at the next check-in`
      : order.detail || `${what} in progress`;
  return (
    <Badge tone="brand" icon={order.type === 'update' ? LoaderCircle : RefreshCw} spin={order.status !== 'pending'}>
      {text}
    </Badge>
  );
}

const BUTTONS = {
  primary: 'bg-brand-600 text-white hover:bg-brand-700',
  soft: 'bg-brand-50 text-brand-700 hover:bg-brand-100',
  plain: 'border border-line bg-white text-ink hover:bg-brand-50',
  danger: 'bg-red-600 text-white hover:bg-red-700',
};

export function Button({
  kind = 'plain',
  icon: Icon,
  className = '',
  children,
  ...rest
}: ComponentProps<'button'> & { kind?: keyof typeof BUTTONS; icon?: LucideIcon }) {
  return (
    <button
      type="button"
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-xl px-3.5 py-2 text-sm font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${BUTTONS[kind]} ${className}`}
      {...rest}
    >
      {Icon && <Icon className="size-4" aria-hidden />}
      {children}
    </button>
  );
}

const ICON_TONES = {
  plain: 'text-ink hover:bg-brand-50',
  brand: 'text-brand-700 hover:bg-brand-50',
  danger: 'text-red-700 hover:bg-red-50',
  good: 'text-emerald-700 hover:bg-emerald-50',
};

/** A small action in a table row. The tip is on a wrapper so it also shows when disabled. */
export function IconButton({
  icon: Icon,
  label,
  tip,
  tone = 'plain',
  disabled,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  tip: string;
  tone?: keyof typeof ICON_TONES;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <span title={tip} className="inline-flex">
      <button
        type="button"
        aria-label={label}
        disabled={disabled}
        onClick={onClick}
        className={`border-line flex size-9 items-center justify-center rounded-lg border bg-white transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${ICON_TONES[tone]}`}
      >
        <Icon className="size-4" aria-hidden />
      </button>
    </span>
  );
}

export function Stat({ label, value, note, icon: Icon, children }: { label: string; value: ReactNode; note?: ReactNode; icon?: LucideIcon; children?: ReactNode }) {
  return (
    <Card>
      <div className="text-muted flex items-center justify-between gap-2 text-sm font-semibold">
        {label}
        {Icon && <Icon className="text-brand-600 size-5 shrink-0" aria-hidden />}
      </div>
      <div className="mt-1 text-3xl font-extrabold tracking-tight">{value}</div>
      {note && <div className="text-muted mt-0.5 text-sm">{note}</div>}
      {children}
    </Card>
  );
}

/** A share of a limit. Turns amber at the warning level and red at the limit, with words. */
export function Meter({ value, limit, warnPercent = 80 }: { value: number; limit: number; warnPercent?: number }) {
  const percent = limit > 0 ? (value / limit) * 100 : 0;
  const color = percent >= 100 ? 'bg-red-600' : percent >= warnPercent ? 'bg-amber-500' : 'bar-gradient';
  return (
    <div
      role="meter"
      aria-valuenow={Math.round(percent)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Share of the limit used"
      className="bg-brand-100 mt-2 h-2 overflow-hidden rounded-full"
    >
      <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(percent, 100)}%` }} />
    </div>
  );
}

export function Empty({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="px-4 py-10 text-center">
      <span className="bg-brand-50 mx-auto flex size-12 items-center justify-center rounded-full">
        <Icon className="text-brand-600 size-6" aria-hidden />
      </span>
      <p className="mt-3 font-bold">{title}</p>
      {children && <div className="text-muted mx-auto mt-1 max-w-md text-sm">{children}</div>}
    </div>
  );
}

export function Problem({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="mb-4 flex items-start gap-2 rounded-xl bg-red-50 px-4 py-3 text-sm font-semibold text-red-800">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
      {children}
    </p>
  );
}

export function Loading() {
  return (
    <div className="text-muted flex items-center justify-center gap-2 py-16 font-semibold">
      <LoaderCircle className="size-5 animate-spin" aria-hidden />
      Loading
    </div>
  );
}

export function Confirm({
  title,
  children,
  action,
  danger,
  busy,
  onConfirm,
  onClose,
}: {
  title: string;
  children: ReactNode;
  action: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      onClose={onClose}
      className="m-auto w-[calc(100%-2rem)] max-w-md rounded-2xl p-5 shadow-xl backdrop:bg-black/40"
    >
      <h2 className="text-ink text-lg font-extrabold">{title}</h2>
      <div className="text-muted mt-2 text-sm">{children}</div>
      <div className="mt-5 flex justify-end gap-2">
        <Button onClick={() => dialog.current?.close()}>Cancel</Button>
        <Button kind={danger ? 'danger' : 'primary'} disabled={busy} onClick={onConfirm} icon={busy ? LoaderCircle : danger ? Power : undefined}>
          {action}
        </Button>
      </div>
    </dialog>
  );
}
