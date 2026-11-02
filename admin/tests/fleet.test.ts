import { createHmac } from 'node:crypto';
import { beforeEach, describe, expect, it } from 'vitest';
import { resetDbForTests } from '@/lib/db';
import {
  addRelease,
  cancelCommand,
  costOf,
  deviceHistory,
  enroll,
  FleetError,
  heartbeat,
  listDevices,
  queueCommand,
  removeDevice,
  setActive,
  updateDevice,
  usageSummary,
} from '@/lib/fleet';
import { licenseIsValid } from '@/lib/license';
import { DEFAULT_SETTINGS, getSettings, saveSettings } from '@/lib/settings';

const SECRET = 'test-secret';
const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const NOW = Date.parse('2026-11-15T12:00:00Z');

function code(body = 'AS7KJJHH') {
  const hash = createHmac('sha256', SECRET).update(body, 'ascii').digest();
  const check = [0, 1, 2, 3].map((i) => ALPHABET[hash[i] % 32]).join('');
  return `${body.slice(0, 4)}-${body.slice(4)}-${check}`;
}

async function join(name = 'PC-1') {
  const joined = await enroll({ license: code(), hostname: name, windowsUser: 'sam', version: 'v1' }, NOW);
  return joined!;
}

const up = { parts: { gatekeeper: true, agent: true, web: true } };
const device = async (id: string, now = NOW) => (await listDevices(now)).find((d) => d.id === id)!;
const release = (version = 'v2') =>
  addRelease({ version, url: 'https://x.example/a.zip', sha256: 'a'.repeat(64), signature: 'sig' }, 'admin', NOW);

beforeEach(() => {
  process.env.ADMIN_DATA_DIR = 'memory://';
  process.env.LICENSE_SECRET = SECRET;
  delete process.env.DATABASE_URL;
  resetDbForTests();
});

describe('joining', () => {
  it('needs a real license code, in any spelling', async () => {
    expect(licenseIsValid(code().toLowerCase().replace(/-/g, ' '), SECRET)).toBe(true);
    expect(await enroll({ license: 'AAAA-BBBB-CCCC' }, NOW)).toBeNull();
    expect(await enroll({ license: code() }, NOW)).toMatchObject({ deviceId: expect.any(String) });
  });

  it('a wrong token gets nothing', async () => {
    await join();
    expect(await heartbeat('not-the-token', up, NOW)).toBeNull();
  });
});

describe('status', () => {
  it('online means checked in lately; up or down is about HireAce itself', async () => {
    const { deviceId, token } = await join();
    await heartbeat(token, up, NOW);
    expect((await device(deviceId)).state).toBe('up');

    await heartbeat(token, { parts: { gatekeeper: true, agent: false, web: true } }, NOW);
    expect((await device(deviceId)).state).toBe('partial');

    await heartbeat(token, { parts: {} }, NOW);
    const down = await device(deviceId);
    expect(down.state).toBe('down');
    expect(down.online).toBe(true);

    const later = NOW + (DEFAULT_SETTINGS.offlineAfterSeconds + 1) * 1000;
    const gone = await device(deviceId, later);
    expect(gone.state).toBe('offline');
    expect(gone.online).toBe(false);
  });
});

describe('orders', () => {
  it('reach the workstation once, in the answer to its check-in', async () => {
    const { deviceId, token } = await join();
    await queueCommand([deviceId], 'restart', 'admin', null, NOW);

    const first = await heartbeat(token, up, NOW);
    expect(first!.command).toMatchObject({ type: 'restart' });
    expect((await heartbeat(token, up, NOW))!.command).toBeNull();

    await heartbeat(token, { ...up, results: [{ id: first!.command!.id, status: 'done' }] }, NOW);
    expect((await device(deviceId)).order).toBeNull();
  });

  it('wait until a call has ended', async () => {
    const { deviceId, token } = await join();
    await queueCommand([deviceId], 'restart', 'admin', null, NOW);
    expect((await heartbeat(token, { ...up, inCall: true }, NOW))!.command).toBeNull();
    expect((await device(deviceId)).order?.status).toBe('pending');
    expect((await heartbeat(token, up, NOW))!.command).not.toBeNull();
  });

  it('an update carries the signature and is not repeated on a PC that has it', async () => {
    const { deviceId, token } = await join();
    await release('v2');
    expect(await queueCommand([deviceId], 'update', 'admin', null, NOW)).toEqual({ queued: 1, version: 'v2' });
    const { command } = (await heartbeat(token, up, NOW))!;
    expect(command).toMatchObject({ type: 'update', version: 'v2', signature: 'sig', sha256: 'a'.repeat(64) });

    await heartbeat(token, { ...up, version: 'v2', results: [{ id: command!.id, status: 'done' }] }, NOW);
    expect(await queueCommand([deviceId], 'update', 'admin', null, NOW)).toEqual({ queued: 0, version: 'v2' });
  });

  it('shows an update in progress, and lets the next order through when it ends', async () => {
    const { deviceId, token } = await join();
    await release();
    await queueCommand([deviceId], 'update', 'admin', null, NOW);
    await queueCommand([deviceId], 'restart', 'admin', null, NOW + 1);
    const { command } = (await heartbeat(token, up, NOW))!;
    await heartbeat(token, { ...up, results: [{ id: command!.id, status: 'running', detail: 'Installing' }] }, NOW);
    expect((await device(deviceId)).state).toBe('updating');
    expect((await heartbeat(token, up, NOW))!.command).toBeNull(); // one at a time
    const after = await heartbeat(
      token,
      { ...up, results: [{ id: command!.id, status: 'failed', detail: 'No network' }] },
      NOW,
    );
    expect(after!.command).toMatchObject({ type: 'restart' });
  });

  it('a stale restart is dropped, a stuck one fails, and waiting ones can be cancelled', async () => {
    const { deviceId, token } = await join();
    await queueCommand([deviceId], 'restart', 'admin', null, NOW);
    const later = NOW + 2 * 3_600_000;
    await heartbeat(token, up, later);
    expect((await device(deviceId, later)).order).toBeNull();

    await queueCommand([deviceId], 'restart', 'admin', null, later);
    expect((await heartbeat(token, up, later))!.command).toBeTruthy();
    const muchLater = later + 2 * 3_600_000;
    await heartbeat(token, up, muchLater);
    expect((await device(deviceId, muchLater)).order).toBeNull();

    await release();
    await queueCommand([deviceId], 'update', 'admin', null, muchLater);
    expect((await device(deviceId, muchLater)).order?.status).toBe('pending');
    const [waiting] = await deviceHistory(deviceId);
    expect(await cancelCommand(waiting.id, 'admin', muchLater)).toBe(true);
    expect((await device(deviceId, muchLater)).order).toBeNull();
  });

  it('another workstation cannot report on an order', async () => {
    const one = await join('PC-1');
    const two = await join('PC-2');
    await queueCommand([one.deviceId], 'restart', 'admin', null, NOW);
    const { command } = (await heartbeat(one.token, up, NOW))!;
    await heartbeat(two.token, { ...up, results: [{ id: command!.id, status: 'done' }] }, NOW);
    expect((await device(one.deviceId)).order?.status).toBe('sent');
  });
});

describe('deactivating', () => {
  it('is told at the next check-in and drops waiting orders', async () => {
    const { deviceId, token } = await join();
    await queueCommand([deviceId], 'restart', 'admin', null, NOW);
    await setActive(deviceId, false, 'admin', NOW);
    const answer = await heartbeat(token, up, NOW);
    expect(answer).toMatchObject({ active: false, command: null });
    expect((await device(deviceId)).state).toBe('deactivated');
    expect((await queueCommand([deviceId], 'restart', 'admin', null, NOW)).queued).toBe(0);

    await setActive(deviceId, true, 'admin', NOW);
    expect((await heartbeat(token, up, NOW))!.active).toBe(true);
  });

  it('a removed workstation loses access', async () => {
    const { deviceId, token } = await join();
    expect(await removeDevice(deviceId, 'admin', NOW)).toBe(true);
    expect(await heartbeat(token, up, NOW)).toBeNull();
  });
});

describe('usage and limits', () => {
  const million = (item = {}) => ({ day: '2026-11-15', model: 'gpt-realtime-2.1', ...item });

  it('prices cached tokens lower', () => {
    const prices = DEFAULT_SETTINGS.prices;
    expect(costOf(million({ inAudio: 1_000_000 }), prices)).toBeCloseTo(32);
    expect(costOf(million({ inAudio: 1_000_000, cachedAudio: 1_000_000 }), prices)).toBeCloseTo(0.4);
    expect(costOf(million({ inText: 500_000, cachedText: 500_000, outAudio: 1_000_000 }), prices)).toBeCloseTo(64.2);
  });

  it('counts a batch once even when it is sent again', async () => {
    const { deviceId, token } = await join();
    const usage = { batchId: 'b1', items: [million({ outAudio: 1_000_000 })] };
    await heartbeat(token, { ...up, usage }, NOW);
    await heartbeat(token, { ...up, usage }, NOW);
    expect((await device(deviceId)).monthCostUsd).toBeCloseTo(64);
    const summary = await usageSummary(NOW);
    expect(summary.monthCostUsd).toBeCloseTo(64);
    expect(summary.daily.at(-1)).toMatchObject({ day: '2026-11-15' });
    expect(summary.onPaceUsd).toBeCloseTo(128);
  });

  it('never refuses calls by default; blocks when told to, at the right limit', async () => {
    const one = await join('PC-1');
    const two = await join('PC-2');
    await saveSettings({ ...(await getSettings()), monthlyBudgetUsd: 50 });
    const usage = { batchId: 'b1', items: [million({ outAudio: 1_000_000 })] };
    expect((await heartbeat(one.token, { ...up, usage }, NOW))!.limitReached).toBe(false);

    await saveSettings({ ...(await getSettings()), atLimit: 'block' });
    expect((await heartbeat(one.token, up, NOW))!.limitReached).toBe(true);
    expect((await heartbeat(two.token, up, NOW))!.limitReached).toBe(true); // the shared budget

    await saveSettings({ ...(await getSettings()), monthlyBudgetUsd: null, deviceMonthlyUsd: 50 });
    expect((await heartbeat(one.token, up, NOW))!.limitReached).toBe(true);
    expect((await heartbeat(two.token, up, NOW))!.limitReached).toBe(false); // spent nothing

    await updateDevice(one.deviceId, { monthlyLimitUsd: 100 }, 'admin', NOW);
    expect((await heartbeat(one.token, up, NOW))!.limitReached).toBe(false); // its own limit

    // A new month starts again
    await updateDevice(one.deviceId, { monthlyLimitUsd: null }, 'admin', NOW);
    const nextMonth = Date.parse('2026-12-01T00:00:00Z');
    expect((await heartbeat(one.token, up, nextMonth))!.limitReached).toBe(false);
  });

  it('refuses settings that make no sense', async () => {
    const errors = await saveSettings({
      ...DEFAULT_SETTINGS,
      monthlyBudgetUsd: -1,
      heartbeatSeconds: 5,
      warnPercent: 0,
    });
    expect(Object.keys(errors).sort()).toEqual(['heartbeatSeconds', 'monthlyBudgetUsd', 'warnPercent']);
    expect((await getSettings()).monthlyBudgetUsd).toBeNull();
  });
});

describe('releases', () => {
  it('must be signed, and each version is published once', async () => {
    await expect(addRelease({ version: 'v2', url: 'https://x/a.zip', sha256: 'a'.repeat(64) }, 'a', NOW)).rejects.toThrow(
      FleetError,
    );
    await release('v2');
    await expect(release('v2')).rejects.toThrow('already published');
  });
});
