'use client';

import { ArrowLeft, CheckCircle2, CircleOff, PackageCheck, PhoneCall, Power, RefreshCw, Trash2, XCircle } from 'lucide-react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useState } from 'react';
import { DailyBars } from '@/components/charts';
import { OrderDialog, type OrderType } from '@/components/orders';
import { Badge, Button, Card, CardTitle, Confirm, Loading, Meter, OrderNote, Page, Problem, StateBadge } from '@/components/ui';
import { call, usePoll } from '@/lib/client';
import { ago, dateTime, duration, usd } from '@/lib/format';
import type { DeviceData } from '@/lib/types';

const STATUS: Record<string, string> = {
  pending: 'Waiting',
  sent: 'Sent',
  running: 'In progress',
  done: 'Done',
  failed: 'Failed',
  expired: 'Expired',
  cancelled: 'Cancelled',
};

export default function WorkstationPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data, error, reload } = usePoll<DeviceData>(`/api/admin/devices/${id}`);
  const [order, setOrder] = useState<OrderType | null>(null);
  const [removing, setRemoving] = useState(false);
  const [message, setMessage] = useState('');
  const [name, setName] = useState<string | null>(null);
  const [limit, setLimit] = useState<string | null>(null);
  const [saveError, setSaveError] = useState('');

  if (!data) return error ? <Problem>{error}</Problem> : <Loading />;
  const { device, history, daily, latestVersion } = data;
  const isLatest = !latestVersion || device.version === latestVersion;
  // Stopping or changing a PC midway through an update makes it roll back
  const updating = device.state === 'updating';

  async function save(changes: Record<string, unknown>) {
    setSaveError('');
    try {
      await call(`/api/admin/devices/${id}`, 'PATCH', changes);
      setMessage('Saved.');
      setName(null);
      setLimit(null);
      reload();
    } catch (problem) {
      setSaveError(problem instanceof Error ? problem.message : 'Could not save.');
    }
  }

  async function cancel(commandId: string) {
    await call(`/api/admin/commands?id=${commandId}`, 'DELETE');
    reload();
  }

  const parts: [string, boolean][] = [
    ['Gatekeeper', device.parts.gatekeeper],
    ['Voice agent', device.parts.agent],
    ['Web app', device.parts.web],
  ];
  const memory =
    device.memoryFreeMb !== null && device.memoryTotalMb
      ? `${(device.memoryFreeMb / 1024).toFixed(1)} of ${(device.memoryTotalMb / 1024).toFixed(1)} GB free`
      : 'Unknown';
  const limitValue = limit ?? (device.monthlyLimitUsd === null ? '' : String(device.monthlyLimitUsd));

  return (
    <Page
      title={device.name}
      intro={`Checked in ${ago(device.lastSeen)} · ${device.windowsUser || 'Unknown user'} on ${device.hostname || 'unknown PC'}`}
    >
      <Link href="/workstations" className="text-brand-700 mb-3 -mt-2 inline-flex items-center gap-1 text-sm font-bold">
        <ArrowLeft className="size-4" aria-hidden />
        All workstations
      </Link>
      {error && <Problem>Could not refresh. Showing the last known status.</Problem>}
      {message && (
        <p role="status" className="bg-brand-50 text-brand-700 mb-3 rounded-xl px-4 py-2.5 text-sm font-bold">
          {message}
        </p>
      )}

      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <StateBadge state={device.state} />
          {device.online && device.inCall && (
            <Badge tone="brand" icon={PhoneCall}>
              In a call
            </Badge>
          )}
          <OrderNote device={device} />
        </div>
        <div className="mt-4 grid grid-cols-1 gap-2 sm:flex sm:flex-wrap">
          <Button kind="primary" icon={PackageCheck} disabled={!device.active || isLatest || updating} onClick={() => setOrder('update')}>
            {updating ? 'Updating now' : !latestVersion ? 'No release yet' : isLatest ? 'On the latest version' : `Install ${latestVersion}`}
          </Button>
          <Button icon={RefreshCw} disabled={!device.active || updating} onClick={() => setOrder('restart')}>
            Restart
          </Button>
          {device.active ? (
            <Button icon={Power} disabled={updating} onClick={() => setOrder('deactivate')}>
              Deactivate
            </Button>
          ) : (
            <Button kind="soft" icon={Power} onClick={() => setOrder('activate')}>
              Activate
            </Button>
          )}
          <Button icon={Trash2} disabled={updating} onClick={() => setRemoving(true)}>
            Remove
          </Button>
        </div>
        {!device.online && device.active && (
          <p className="text-muted mt-3 text-sm">This PC is offline. Orders wait until it is back, if they have not expired.</p>
        )}
      </Card>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle>Health</CardTitle>
          <ul className="mb-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
            {parts.map(([part, running]) => (
              <li key={part} className="bg-page flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold">
                {!device.online ? (
                  <CircleOff className="text-muted size-4" aria-hidden />
                ) : running ? (
                  <CheckCircle2 className="size-4 text-emerald-600" aria-hidden />
                ) : (
                  <XCircle className="size-4 text-red-600" aria-hidden />
                )}
                {part}
                <span className="sr-only">{!device.online ? 'unknown' : running ? 'running' : 'stopped'}</span>
              </li>
            ))}
          </ul>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <div>
              <dt className="text-muted">Version</dt>
              <dd className="font-bold break-words">{device.version || 'Unknown'}</dd>
            </div>
            <div>
              <dt className="text-muted">License</dt>
              <dd className="font-bold">{device.license}</dd>
            </div>
            <div>
              <dt className="text-muted">Memory</dt>
              <dd className="font-bold">{memory}</dd>
            </div>
            <div>
              <dt className="text-muted">Disk free</dt>
              <dd className="font-bold">{device.diskFreeGb !== null ? `${Math.round(device.diskFreeGb)} GB` : 'Unknown'}</dd>
            </div>
            <div>
              <dt className="text-muted">PC running for</dt>
              <dd className="font-bold">{device.uptimeSeconds !== null ? duration(device.uptimeSeconds) : 'Unknown'}</dd>
            </div>
            <div>
              <dt className="text-muted">Joined</dt>
              <dd className="font-bold">{dateTime(device.enrolledAt)}</dd>
            </div>
          </dl>
        </Card>

        <Card>
          <CardTitle>This month</CardTitle>
          <div className="text-3xl font-extrabold tracking-tight">{usd(device.monthCostUsd)}</div>
          <div className="text-muted text-sm">
            {device.limitUsd !== null
              ? `of ${usd(device.limitUsd)}${device.monthlyLimitUsd === null ? ' (shared per-workstation limit)' : ''}`
              : 'No limit set'}
          </div>
          {device.limitUsd !== null && <Meter value={device.monthCostUsd} limit={device.limitUsd} />}

          {saveError && <div className="mt-3"><Problem>{saveError}</Problem></div>}
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="name" className="text-sm font-semibold">
                Display name
              </label>
              <div className="mt-1 flex gap-2">
                <input
                  id="name"
                  value={name ?? device.label}
                  placeholder={device.hostname}
                  onChange={(event) => setName(event.target.value)}
                  className="bg-field border-line focus:border-brand-500 h-10 min-w-0 flex-1 rounded-xl border px-3 text-sm outline-none focus:bg-white"
                />
                <Button disabled={name === null} onClick={() => save({ label: name })}>
                  Save
                </Button>
              </div>
            </div>
            <div>
              <label htmlFor="limit" className="text-sm font-semibold">
                Own monthly limit (US$)
              </label>
              <div className="mt-1 flex gap-2">
                <input
                  id="limit"
                  inputMode="decimal"
                  value={limitValue}
                  placeholder="Shared limit"
                  onChange={(event) => setLimit(event.target.value)}
                  className="bg-field border-line focus:border-brand-500 h-10 min-w-0 flex-1 rounded-xl border px-3 text-sm outline-none focus:bg-white"
                />
                <Button
                  disabled={limit === null}
                  onClick={() => save({ monthlyLimitUsd: limit?.trim() ? Number(limit) : null })}
                >
                  Save
                </Button>
              </div>
            </div>
          </div>
        </Card>
      </div>

      <Card className="mt-4">
        <CardTitle hint="Last 30 days, estimate">OpenAI spend per day</CardTitle>
        <DailyBars daily={daily} />
      </Card>

      <Card className="mt-4">
        <CardTitle>Orders</CardTitle>
        {history.length === 0 ? (
          <p className="text-muted text-sm">None yet.</p>
        ) : (
          <ul className="divide-line scroll-thin max-h-80 divide-y overflow-y-auto text-sm">
            {history.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2.5">
                <span className="min-w-0">
                  <strong>{row.type === 'update' ? `Install ${row.version ?? 'a removed release'}` : 'Restart'}</strong>
                  <span className="text-muted"> · {row.created_by} · {ago(row.created_at)}</span>
                  {row.detail && <span className="text-muted block break-words">{row.detail}</span>}
                </span>
                <span className="flex items-center gap-2">
                  <Badge tone={row.status === 'done' ? 'good' : row.status === 'failed' ? 'bad' : row.status === 'pending' || row.status === 'sent' || row.status === 'running' ? 'brand' : 'off'}>
                    {STATUS[row.status]}
                  </Badge>
                  {row.status === 'pending' && (
                    <button type="button" onClick={() => cancel(row.id)} className="text-brand-700 font-bold">
                      Cancel
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {order && (
        <OrderDialog
          type={order}
          deviceIds={[device.id]}
          name={device.name}
          version={latestVersion}
          onClose={() => setOrder(null)}
          onDone={(text) => {
            setMessage(text);
            setOrder(null);
            reload();
          }}
        />
      )}
      {removing && (
        <Confirm
          title={`Remove ${device.name}?`}
          action="Remove"
          danger
          onClose={() => setRemoving(false)}
          onConfirm={async () => {
            await call(`/api/admin/devices/${id}`, 'DELETE');
            router.push('/workstations');
          }}
        >
          For a PC that is retired. Its history and usage are deleted, and this month&apos;s total drops by its spend. If the PC
          is still running HireAce it joins again as a new workstation at its next start: to stop it, deactivate it instead.
        </Confirm>
      )}
    </Page>
  );
}
