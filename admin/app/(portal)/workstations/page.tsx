'use client';

import { ChevronRight, Monitor, PackageCheck, PhoneCall, Power, RefreshCw, Search } from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { OrderDialog, type OrderType } from '@/components/orders';
import { Badge, Button, Card, Empty, IconButton, Loading, OrderNote, Page, Problem, RefreshTimer, StateBadge } from '@/components/ui';
import { usePoll } from '@/lib/client';
import { ago, usd } from '@/lib/format';
import type { DevicesData, DeviceView } from '@/lib/types';

// short: what fits on a phone, where they share one row
const FILTERS: { key: string; label: string; short: string; test: (device: DeviceView) => boolean }[] = [
  { key: 'all', label: 'All', short: 'All', test: () => true },
  { key: 'online', label: 'Online', short: 'Online', test: (d) => d.active && d.online },
  { key: 'offline', label: 'Offline', short: 'Offline', test: (d) => d.active && !d.online },
  { key: 'off', label: 'Deactivated', short: 'Inactive', test: (d) => !d.active },
];

/** Nothing else may be ordered while a PC updates: stopping it midway makes it roll back. */
const isUpdating = (device: DeviceView) => device.state === 'updating';

interface Order {
  type: OrderType;
  deviceIds: string[];
  name: string;
}

/** Why a workstation cannot take the latest version; empty when it can. */
function installBlocked(device: DeviceView, latest: string | null): string {
  if (device.state === 'updating') return 'Updating now';
  if (!latest) return 'No release yet';
  if (!device.active) return 'Deactivated';
  if (device.version === latest) return `Already on ${latest}`;
  return '';
}

export default function WorkstationsPage() {
  const { data, error, reload, lastAt, everyMs } = usePoll<DevicesData>('/api/admin/devices', 5_000);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [order, setOrder] = useState<Order | null>(null);
  const [message, setMessage] = useState('');

  const rows = useMemo(() => {
    const test = FILTERS.find((item) => item.key === filter)!.test;
    const words = search.trim().toLowerCase();
    return (data?.devices ?? []).filter(
      (device) =>
        test(device) &&
        (!words || `${device.name} ${device.hostname} ${device.windowsUser} ${device.license}`.toLowerCase().includes(words)),
    );
  }, [data, filter, search]);

  if (!data) return error ? <Problem>{error}</Problem> : <Loading />;

  const latest = data.latestVersion;
  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  const allShown = rows.length > 0 && rows.every((row) => selected.has(row.id));
  const chosen = data.devices.filter((device) => selected.has(device.id));
  const ask = (type: OrderType, devices: DeviceView[]) =>
    setOrder({
      type,
      deviceIds: devices.map((device) => device.id),
      name: devices.length === 1 ? devices[0].name : `${devices.length} workstations`,
    });

  // The three actions, for one workstation or for all those selected
  const rowActions = (device: DeviceView) => (
    <>
      <IconButton
        icon={PackageCheck}
        label={latest ? `Install ${latest} on ${device.name}` : `Install the latest version on ${device.name}`}
        tip={installBlocked(device, latest) || `Install ${latest}`}
        tone="brand"
        disabled={Boolean(installBlocked(device, latest))}
        onClick={() => ask('update', [device])}
      />
      <IconButton
        icon={RefreshCw}
        label={`Restart ${device.name}`}
        tip={isUpdating(device) ? 'Updating now' : device.active ? 'Restart' : 'Deactivated'}
        disabled={!device.active || isUpdating(device)}
        onClick={() => ask('restart', [device])}
      />
      <IconButton
        icon={Power}
        label={`${device.active ? 'Deactivate' : 'Activate'} ${device.name}`}
        tip={isUpdating(device) ? 'Updating now' : device.active ? 'Deactivate' : 'Activate'}
        tone={device.active ? 'danger' : 'good'}
        disabled={isUpdating(device)}
        onClick={() => ask(device.active ? 'deactivate' : 'activate', [device])}
      />
    </>
  );
  const canInstall = chosen.filter((device) => !installBlocked(device, latest));
  const canRestart = chosen.filter((device) => device.active && !isUpdating(device));
  const allOff = chosen.length > 0 && chosen.every((device) => !device.active);
  const bulkActions = (
    <>
      <IconButton
        icon={PackageCheck}
        label={`Install the latest version on ${chosen.length} selected`}
        tip={canInstall.length ? `Install ${latest} on ${canInstall.length}` : 'None of these can take it'}
        tone="brand"
        disabled={!canInstall.length}
        onClick={() => ask('update', canInstall)}
      />
      <IconButton
        icon={RefreshCw}
        label={`Restart ${chosen.length} selected`}
        tip={canRestart.length ? `Restart ${canRestart.length}` : 'None of these can restart now'}
        disabled={!canRestart.length}
        onClick={() => ask('restart', canRestart)}
      />
      <IconButton
        icon={Power}
        label={`${allOff ? 'Activate' : 'Deactivate'} ${chosen.length} selected`}
        tip={allOff ? `Activate ${chosen.length}` : canRestart.length ? `Deactivate ${canRestart.length}` : 'Updating now'}
        tone={allOff ? 'good' : 'danger'}
        disabled={!allOff && !canRestart.length}
        onClick={() => (allOff ? ask('activate', chosen) : ask('deactivate', canRestart))}
      />
    </>
  );

  return (
    <Page
      fill
      actions={<RefreshTimer lastAt={lastAt} everyMs={everyMs} onRefresh={reload} />}
      title="Workstations"
      intro="Online means HireAce is running on that PC. It shows as offline within seconds of being closed."
    >
      {error && <Problem>Could not refresh. Showing the last known status.</Problem>}
      {message && (
        <p role="status" className="bg-brand-50 text-brand-700 mb-3 rounded-xl px-4 py-2.5 text-sm font-bold">
          {message}
        </p>
      )}

      <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative min-w-0 flex-1">
          <Search className="text-muted absolute top-3 left-3.5 size-4" aria-hidden />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by name, user or license"
            aria-label="Search workstations"
            className="border-line focus:border-brand-500 h-10 w-full rounded-xl border bg-white pr-3 pl-10 text-sm outline-none"
          />
        </div>
        {/* Phones: one neat bar of equal parts. Wider: separate pills. */}
        <div
          role="group"
          aria-label="Show"
          className="border-line grid grid-cols-4 gap-0.5 rounded-xl border bg-white p-1 sm:flex sm:gap-1.5 sm:border-0 sm:bg-transparent sm:p-0"
        >
          {FILTERS.map(({ key, label, short }) => (
            <button
              key={key}
              type="button"
              aria-pressed={filter === key}
              aria-label={label}
              onClick={() => setFilter(key)}
              className={`min-w-0 rounded-lg py-2 text-xs font-bold transition-colors sm:shrink-0 sm:rounded-full sm:px-3 sm:py-1.5 sm:text-sm ${
                filter === key ? 'bg-brand-600 text-white' : 'text-muted hover:bg-brand-50 sm:border-line sm:border sm:bg-white'
              }`}
            >
              <span className="sm:hidden">{short}</span>
              <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </div>
      </div>

      {data.devices.length === 0 ? (
        <Card>
          <Empty icon={Monitor} title="No workstations yet">
            Install HireAce on a PC with an installer built for this portal. It joins with its license code and appears here
            within a minute.
          </Empty>
        </Card>
      ) : rows.length === 0 ? (
        <Card>
          <Empty icon={Search} title="Nothing matches that" />
        </Card>
      ) : (
        <>
          {/* Wide screens: a table */}
          <Card className="scroll-thin hidden min-h-0 flex-initial overflow-y-auto p-0! md:block">
            <table className="w-full text-sm">
              <thead className="bg-page text-muted sticky top-0 z-10 text-left">
                <tr>
                  <th className="w-10 px-4 py-3">
                    <input
                      type="checkbox"
                      aria-label="Select all shown"
                      checked={allShown}
                      onChange={() => setSelected(allShown ? new Set() : new Set(rows.map((row) => row.id)))}
                      className="accent-brand-600 size-4"
                    />
                  </th>
                  <th className="py-3 pr-3 font-semibold">Workstation</th>
                  <th className="py-3 pr-3 font-semibold">Status</th>
                  <th className="py-3 pr-3 font-semibold">Version</th>
                  <th className="hidden py-3 pr-3 text-right font-semibold xl:table-cell">This month</th>
                  <th className="py-3 pr-3 text-right font-semibold whitespace-nowrap">Checked in</th>
                  <th className="py-2 pr-4 text-right font-semibold whitespace-nowrap">
                    {chosen.length ? (
                      <span className="flex items-center justify-end gap-1">
                        <span className="text-ink mr-1 font-bold">{chosen.length} selected</span>
                        {bulkActions}
                      </span>
                    ) : (
                      'Actions'
                    )}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((device) => (
                  <tr key={device.id} className="border-line hover:bg-page border-t">
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        aria-label={`Select ${device.name}`}
                        checked={selected.has(device.id)}
                        onChange={() => toggle(device.id)}
                        className="accent-brand-600 size-4"
                      />
                    </td>
                    <td className="py-3 pr-3">
                      <Link href={`/workstations/${device.id}`} className="hover:text-brand-700 font-bold">
                        {device.name}
                      </Link>
                      <div className="text-muted text-xs">{device.windowsUser || device.hostname}</div>
                    </td>
                    <td className="py-3 pr-3">
                      <div className="flex flex-wrap gap-1.5">
                        <StateBadge state={device.state} />
                        {device.online && device.inCall && (
                          <Badge tone="brand" icon={PhoneCall}>
                            In a call
                          </Badge>
                        )}
                        <OrderNote device={device} />
                      </div>
                    </td>
                    <td className="py-3 pr-3">
                      <span className="font-semibold">{device.version || 'Unknown'}</span>
                      {latest && device.version !== latest && (
                        <div className="text-xs font-semibold text-amber-800">Update available</div>
                      )}
                    </td>
                    <td className="hidden py-3 pr-3 text-right font-semibold tabular-nums xl:table-cell">{usd(device.monthCostUsd)}</td>
                    <td className="text-muted py-3 pr-3 text-right whitespace-nowrap">{ago(device.lastSeen)}</td>
                    <td className="py-2 pr-4">
                      <div className="flex justify-end gap-1">{rowActions(device)}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          {/* Phones: cards, each with its own actions */}
          {chosen.length > 0 && (
            <div className="bg-brand-50 mb-3 flex items-center justify-between gap-2 rounded-xl px-3 py-2 md:hidden">
              <span className="text-sm font-bold">{chosen.length} selected</span>
              <span className="flex gap-1">{bulkActions}</span>
            </div>
          )}
          <ul className="scroll-thin min-h-0 flex-initial space-y-3 overflow-y-auto md:hidden">
            {rows.map((device) => (
              <li key={device.id} className="border-line rounded-2xl border bg-white p-4 shadow-sm">
                <div className="flex gap-3">
                  <input
                    type="checkbox"
                    aria-label={`Select ${device.name}`}
                    checked={selected.has(device.id)}
                    onChange={() => toggle(device.id)}
                    className="accent-brand-600 mt-1 size-5 shrink-0"
                  />
                  <Link href={`/workstations/${device.id}`} className="min-w-0 flex-1">
                    <span className="flex items-start justify-between gap-2">
                      <span className="min-w-0">
                        <span className="block truncate font-bold">{device.name}</span>
                        <span className="text-muted block truncate text-xs">{device.windowsUser || device.hostname}</span>
                      </span>
                      <ChevronRight className="text-muted size-5 shrink-0" aria-hidden />
                    </span>
                    <span className="mt-2 flex flex-wrap gap-1.5">
                      <StateBadge state={device.state} />
                      {device.online && device.inCall && (
                        <Badge tone="brand" icon={PhoneCall}>
                          In a call
                        </Badge>
                      )}
                      <OrderNote device={device} />
                    </span>
                    <span className="text-muted mt-2 flex flex-wrap justify-between gap-x-3 text-xs">
                      <span>{device.version || 'Unknown version'}</span>
                      <span>{usd(device.monthCostUsd)} this month</span>
                      <span>{ago(device.lastSeen)}</span>
                    </span>
                  </Link>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2">
                  <Button
                    icon={PackageCheck}
                    aria-label={`Install the latest version on ${device.name}`}
                    disabled={Boolean(installBlocked(device, latest))}
                    onClick={() => ask('update', [device])}
                    className="px-1! text-xs! max-[359px]:[&>svg]:hidden"
                  >
                    Install
                  </Button>
                  <Button
                    icon={RefreshCw}
                    aria-label={`Restart ${device.name}`}
                    disabled={!device.active || isUpdating(device)}
                    onClick={() => ask('restart', [device])}
                    className="px-1! text-xs! max-[359px]:[&>svg]:hidden"
                  >
                    Restart
                  </Button>
                  <Button
                    icon={Power}
                    aria-label={`${device.active ? 'Deactivate' : 'Activate'} ${device.name}`}
                    disabled={isUpdating(device)}
                    onClick={() => ask(device.active ? 'deactivate' : 'activate', [device])}
                    className="px-1! text-xs! max-[359px]:[&>svg]:hidden"
                  >
                    {device.active ? 'Deactivate' : 'Activate'}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      {order && (
        <OrderDialog
          type={order.type}
          deviceIds={order.deviceIds}
          name={order.name}
          version={latest}
          onClose={() => setOrder(null)}
          onDone={(text) => {
            setMessage(text);
            setOrder(null);
            setSelected(new Set());
            reload();
          }}
        />
      )}
    </Page>
  );
}
