'use client';

import { AlertTriangle, CheckCircle2, Monitor, PhoneCall, Wallet, Wifi, XCircle, type LucideIcon } from 'lucide-react';
import Link from 'next/link';
import { DailyBars } from '@/components/charts';
import { Card, CardTitle, Empty, Loading, Meter, Page, Problem, Stat, StateBadge } from '@/components/ui';
import { usePoll } from '@/lib/client';
import { ago, usd } from '@/lib/format';
import type { ActivityRow, AlertsData, DevicesData, UsageData } from '@/lib/types';

interface Alert {
  key: string;
  tone: 'bad' | 'warn';
  icon: LucideIcon;
  text: string;
  href: string;
}

function alerts(fleet: DevicesData, spending: AlertsData | null): Alert[] {
  const list: Alert[] = (spending?.open ?? []).map((alert) => ({
    key: alert.id,
    tone: alert.severity === 'critical' ? 'bad' : 'warn',
    icon: alert.severity === 'critical' ? XCircle : Wallet,
    text: `${alert.title}. ${alert.detail}`,
    href: '/usage',
  }));
  for (const device of fleet.devices) {
    if (device.state === 'partial') {
      const href = `/workstations/${device.id}`;
      list.push({ key: `${device.id}-p`, tone: 'warn', icon: AlertTriangle, text: `${device.name}: part of HireAce is not running.`, href });
    }
  }
  return list;
}

export default function OverviewPage() {
  const fleet = usePoll<DevicesData>('/api/admin/devices', 5_000);
  const usage = usePoll<UsageData>('/api/admin/usage');
  const activity = usePoll<{ activity: ActivityRow[] }>('/api/admin/activity');
  const spending = usePoll<AlertsData>('/api/admin/alerts');

  if (!fleet.data || !usage.data) {
    return fleet.error || usage.error ? <Problem>{fleet.error || usage.error}</Problem> : <Loading />;
  }

  const devices = fleet.data.devices;
  const active = devices.filter((device) => device.active);
  const online = active.filter((device) => device.online);
  const up = active.filter((device) => device.state === 'up');
  const inCall = active.filter((device) => device.online && device.inCall);
  const offline = active.filter((device) => !device.online);
  const outdated = fleet.data.latestVersion
    ? active.filter((device) => device.version !== fleet.data!.latestVersion).length
    : 0;
  const notices = alerts(fleet.data, spending.data);
  const { monthCostUsd, budgetUsd, warnPercent, onPaceUsd, billed } = usage.data;

  return (
    <Page title="Overview">
      {(fleet.error || usage.error) && <Problem>Could not refresh. Showing the last known status.</Problem>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Online" value={`${online.length}/${active.length}`} note={`${offline.length} offline`} icon={Wifi} />
        <Stat label="HireAce up" value={up.length} note="All parts running" icon={CheckCircle2} />
        <Stat label="In a call" value={inCall.length} note="Right now" icon={PhoneCall} />
        <Stat
          label="Spend this month"
          value={usd(billed ? billed.usd : monthCostUsd)}
          note={
            billed
              ? 'Billed by OpenAI, whole organization'
              : budgetUsd !== null
                ? `Estimate, of ${usd(budgetUsd)}`
                : `Estimate · on pace for ${usd(onPaceUsd)}`
          }
          icon={Wallet}
        >
          {!billed && budgetUsd !== null && <Meter value={monthCostUsd} limit={budgetUsd} warnPercent={warnPercent} />}
        </Stat>
      </div>

      {notices.length > 0 && (
        <Card className="mt-4">
          <CardTitle>Needs attention</CardTitle>
          <ul className="divide-line divide-y">
            {notices.map(({ key, tone, icon: Icon, text, href }) => (
              <li key={key}>
                <Link href={href} className="hover:text-brand-700 flex items-start gap-2.5 py-2.5 text-sm font-semibold">
                  <Icon className={`mt-0.5 size-4 shrink-0 ${tone === 'bad' ? 'text-red-600' : 'text-amber-600'}`} aria-hidden />
                  {text}
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardTitle
            hint={
              billed
                ? 'Billed by OpenAI, whole organization. Last 30 days, UTC. Today can be low until OpenAI posts it.'
                : 'Last 30 days, all workstations (estimate)'
            }
          >
            OpenAI spend per day
          </CardTitle>
          <DailyBars daily={billed ? billed.days.slice(-30) : usage.data.daily} />
        </Card>

        <Card className="lg:col-span-2">
          <div className="flex items-baseline justify-between gap-2">
            <CardTitle>Workstations</CardTitle>
            <Link href="/workstations" className="text-brand-700 text-sm font-bold">
              See all
            </Link>
          </div>
          {devices.length === 0 ? (
            <Empty icon={Monitor} title="No workstations yet">
              A PC appears here within a minute of installing HireAce with this portal&apos;s address.
            </Empty>
          ) : (
            <ul className="divide-line divide-y">
              {devices.slice(0, 6).map((device) => (
                <li key={device.id}>
                  <Link href={`/workstations/${device.id}`} className="flex items-center justify-between gap-3 py-2.5">
                    <span className="min-w-0">
                      <span className="block truncate font-bold">{device.name}</span>
                      <span className="text-muted block text-xs">Checked in {ago(device.lastSeen)}</span>
                    </span>
                    <StateBadge state={device.state} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {outdated > 0 && (
            <Link href="/releases" className="bg-brand-50 text-brand-700 mt-3 block rounded-xl px-3 py-2 text-sm font-bold">
              {outdated} not on the latest version ({fleet.data.latestVersion})
            </Link>
          )}
        </Card>
      </div>

      <Card className="mt-4">
        <CardTitle>Recent activity</CardTitle>
        {!activity.data?.activity.length ? (
          <p className="text-muted text-sm">Nothing yet.</p>
        ) : (
          <ul className="divide-line divide-y text-sm">
            {activity.data.activity.slice(0, 6).map((row) => (
              <li key={row.id} className="flex flex-wrap justify-between gap-x-4 py-2">
                <span>
                  <strong>{row.action}</strong>
                  {row.device && ` · ${row.device}`}
                  {row.detail && row.detail !== row.device && <span className="text-muted"> · {row.detail}</span>}
                </span>
                <span className="text-muted">{ago(row.at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </Page>
  );
}
