'use client';

import { ChevronRight, Monitor, PackageCheck, PhoneCall, Power, RefreshCw, Search } from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { OrderDialog, type OrderType } from '@/components/orders';
import { Badge, Button, Card, Empty, Loading, OrderNote, Page, Problem, StateBadge } from '@/components/ui';
import { usePoll } from '@/lib/client';
import { ago, usd } from '@/lib/format';
import type { DevicesData, DeviceView } from '@/lib/types';

const FILTERS: { key: string; label: string; test: (device: DeviceView) => boolean }[] = [
  { key: 'all', label: 'All', test: () => true },
  { key: 'online', label: 'Online', test: (d) => d.active && d.online },
  { key: 'offline', label: 'Offline', test: (d) => d.active && !d.online },
  { key: 'down', label: 'HireAce down', test: (d) => d.state === 'down' || d.state === 'partial' },
  { key: 'off', label: 'Deactivated', test: (d) => !d.active },
];

export default function WorkstationsPage() {
  const { data, error, reload } = usePoll<DevicesData>('/api/admin/devices');
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [order, setOrder] = useState<OrderType | null>(null);
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

  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  const allShown = rows.length > 0 && rows.every((row) => selected.has(row.id));
  const ids = data.devices.filter((device) => selected.has(device.id)).map((device) => device.id);
  const selectedName =
    ids.length === 1 ? data.devices.find((device) => device.id === ids[0])!.name : `${ids.length} workstations`;

  return (
    <Page
      title="Workstations"
      intro={`Each PC checks in every ${data.heartbeatSeconds} seconds. It shows as offline after ${Math.round(data.offlineAfterSeconds / 60)} minutes of silence.`}
    >
      {error && <Problem>Could not refresh. Showing the last known status.</Problem>}
      {message && (
        <p role="status" className="bg-brand-50 text-brand-700 mb-3 rounded-xl px-4 py-2.5 text-sm font-bold">
          {message}
        </p>
      )}

      <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
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
        <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              aria-pressed={filter === key}
              onClick={() => setFilter(key)}
              className={`shrink-0 rounded-full px-3 py-1.5 text-sm font-bold transition-colors ${
                filter === key ? 'bg-brand-600 text-white' : 'border-line text-muted hover:bg-brand-50 border bg-white'
              }`}
            >
              {label}
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
          <Card className="hidden overflow-hidden p-0! md:block">
            <table className="w-full text-sm">
              <thead className="bg-page text-muted text-left">
                <tr>
                  <th className="w-10 px-4 py-3">
                    <input
                      type="checkbox"
                      aria-label="Select all shown"
                      checked={allShown}
                      onChange={() =>
                        setSelected(allShown ? new Set() : new Set(rows.map((row) => row.id)))
                      }
                      className="accent-brand-600 size-4"
                    />
                  </th>
                  <th className="py-3 pr-3 font-semibold">Workstation</th>
                  <th className="py-3 pr-3 font-semibold">Status</th>
                  <th className="py-3 pr-3 font-semibold">Version</th>
                  <th className="py-3 pr-3 text-right font-semibold">This month</th>
                  <th className="py-3 pr-4 text-right font-semibold">Checked in</th>
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
                      {data.latestVersion && device.version !== data.latestVersion && (
                        <div className="text-xs font-semibold text-amber-800">Update available</div>
                      )}
                    </td>
                    <td className="py-3 pr-3 text-right font-semibold tabular-nums">{usd(device.monthCostUsd)}</td>
                    <td className="text-muted py-3 pr-4 text-right whitespace-nowrap">{ago(device.lastSeen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          {/* Phones: cards */}
          <ul className="space-y-3 md:hidden">
            {rows.map((device) => (
              <li key={device.id} className="border-line flex gap-3 rounded-2xl border bg-white p-4 shadow-sm">
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
              </li>
            ))}
          </ul>
        </>
      )}

      {ids.length > 0 && (
        <div className="border-line fixed inset-x-3 bottom-20 z-30 flex flex-wrap items-center justify-between gap-2 rounded-2xl border bg-white p-3 shadow-xl lg:inset-x-auto lg:right-8 lg:bottom-6 lg:left-72">
          <span className="text-sm font-bold">{ids.length} selected</span>
          <div className="flex flex-wrap gap-2">
            <Button kind="primary" icon={PackageCheck} disabled={!data.latestVersion} onClick={() => setOrder('update')}>
              Install latest
            </Button>
            <Button icon={RefreshCw} onClick={() => setOrder('restart')}>
              Restart
            </Button>
            <Button icon={Power} onClick={() => setOrder('deactivate')}>
              Deactivate
            </Button>
          </div>
        </div>
      )}

      {order && (
        <OrderDialog
          type={order}
          deviceIds={ids}
          name={selectedName}
          version={data.latestVersion}
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
