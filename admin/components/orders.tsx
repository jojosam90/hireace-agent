'use client';

import { useState, type ReactNode } from 'react';
import { call } from '@/lib/client';
import { Confirm, Problem } from './ui';

export type OrderType = 'update' | 'restart' | 'deactivate' | 'activate';

const COPY: Record<OrderType, { title: (n: string) => string; action: string; danger?: boolean; body: (version: string | null) => ReactNode }> = {
  update: {
    title: (n) => `Install the latest version on ${n}?`,
    action: 'Install',
    body: (version) => (
      <>
        Installs <strong>{version ?? 'the latest release'}</strong> at the next check-in. HireAce closes while it installs,
        for about 5 minutes, and an open call is never cut off: the update waits for it to end. Anything not saved in Word
        or Excel stays open. If it fails, the PC goes back to the version it had.
      </>
    ),
  },
  restart: {
    title: (n) => `Restart HireAce on ${n}?`,
    action: 'Restart',
    body: () => (
      <>
        Restarts at the next check-in, and also starts HireAce if it was closed, which opens its panel on that screen. An open
        call is never cut off: the restart waits for it to end, for up to an hour.
      </>
    ),
  },
  deactivate: {
    title: (n) => `Deactivate ${n}?`,
    action: 'Deactivate',
    danger: true,
    body: () => (
      <>
        At the next check-in HireAce stops at once, <strong>even during a call</strong>, and will not start until you activate
        it again here. The PC keeps checking in. This does not change the shared OpenAI key, so it does not stop someone who
        has copied that key.
      </>
    ),
  },
  activate: {
    title: (n) => `Activate ${n}?`,
    action: 'Activate',
    body: () => <>HireAce can be started again on that PC from the next check-in.</>,
  },
};

/** Asks before sending an order to one or many workstations. */
export function OrderDialog({
  type,
  deviceIds,
  name,
  version,
  releaseId,
  onDone,
  onClose,
}: {
  type: OrderType;
  deviceIds: string[];
  name: string;
  version: string | null;
  releaseId?: string;
  onDone: (message: string) => void;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const copy = COPY[type];

  async function send() {
    setBusy(true);
    setError('');
    try {
      const { queued } = await call<{ queued: number }>('/api/admin/commands', 'POST', { type, deviceIds, releaseId });
      onDone(
        queued === deviceIds.length
          ? `Sent to ${queued === 1 ? name : `${queued} workstations`}.`
          : `Sent to ${queued} of ${deviceIds.length}: the others are deactivated or already have that version.`,
      );
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Could not send that.');
      setBusy(false);
    }
  }

  return (
    <Confirm title={copy.title(name)} action={copy.action} danger={copy.danger} busy={busy} onConfirm={send} onClose={onClose}>
      {error && <Problem>{error}</Problem>}
      {copy.body(version)}
    </Confirm>
  );
}
