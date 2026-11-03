import { createHmac } from 'node:crypto';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { acknowledgeAlerts, checkSpendAlerts, listAlerts, sendTestEmail } from '@/lib/alerts';
import { resetDbForTests } from '@/lib/db';
import { enroll, heartbeat, spendPeriods, updateDevice, usageHistory } from '@/lib/fleet';
import { getSettings, saveSettings } from '@/lib/settings';

const SECRET = 'test-secret';
const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const NOW = Date.parse('2026-11-15T12:00:00Z');

function code() {
  const hash = createHmac('sha256', SECRET).update('AS7KJJHH', 'ascii').digest();
  return `AS7K-JJHH-${[0, 1, 2, 3].map((i) => ALPHABET[hash[i] % 32]).join('')}`;
}

const join = async (hostname = 'PC-1') => (await enroll({ license: code(), hostname }, NOW))!;

let batch = 0;
/** Spends this many dollars, at the default $64 per 1M audio tokens out. */
function spend(token: string, usd: number, now = NOW, model = 'gpt-realtime-2.1') {
  const day = new Date(now).toISOString().slice(0, 10);
  const items = [{ day, model, responses: 3, outAudio: (usd / 64) * 1_000_000 }];
  return heartbeat(token, { usage: { batchId: `b${++batch}`, items } }, now);
}

const titles = async () => (await listAlerts()).open.map((alert) => alert.title).sort();

beforeEach(() => {
  process.env.ADMIN_DATA_DIR = 'memory://';
  process.env.LICENSE_SECRET = SECRET;
  delete process.env.DATABASE_URL;
  delete process.env.RESEND_API_KEY;
  resetDbForTests();
});

afterEach(() => vi.unstubAllGlobals());

describe('budget alerts', () => {
  it('fires once per step, and a jump past several is one alert', async () => {
    const { token } = await join();
    await saveSettings({ ...(await getSettings()), monthlyBudgetUsd: 100, paceAlert: false });

    await spend(token, 40);
    expect(await titles()).toEqual([]);

    await spend(token, 15);
    expect(await titles()).toEqual(['50% of the monthly budget used']);

    await spend(token, 1);
    expect(await titles()).toHaveLength(1); // same step: not again

    await spend(token, 50);
    const reached = await titles();
    expect(reached).toContain('Monthly budget reached');
    expect(reached).not.toContain('80% of the monthly budget used');
  });

  it('says whether calls continue, and reaching the limit alerts whatever the steps are', async () => {
    const { token } = await join();
    await saveSettings({ ...(await getSettings()), monthlyBudgetUsd: 10, alertPercents: [90], atLimit: 'block' });
    await spend(token, 11);
    const [alert] = (await listAlerts()).open;
    expect(alert.severity).toBe('critical');
    expect(alert.detail).toContain('New calls are refused');
  });

  it('starts again next month', async () => {
    const { token } = await join();
    await saveSettings({ ...(await getSettings()), monthlyBudgetUsd: 10 });
    await spend(token, 11);
    await acknowledgeAlerts(null, 'admin', NOW);
    expect(await titles()).toEqual([]);

    await spend(token, 11, Date.parse('2026-12-05T00:00:00Z'));
    expect(await titles()).toContain('Monthly budget reached');
  });

  it('reaching a raised budget alerts again', async () => {
    const { token } = await join();
    await saveSettings({ ...(await getSettings()), monthlyBudgetUsd: 10, paceAlert: false, alertPercents: [] });
    await spend(token, 11);
    await acknowledgeAlerts(null, 'admin', NOW);

    await saveSettings({ ...(await getSettings()), monthlyBudgetUsd: 20 });
    await spend(token, 1);
    expect(await titles()).toEqual([]); // $12 of $20: not there yet
    await spend(token, 9);
    const [alert] = (await listAlerts()).open;
    expect(alert.title).toBe('Monthly budget reached');
    expect(alert.detail).toContain('of $20.00');
  });

  it('a limit lowered below what was spent alerts without new usage', async () => {
    const { token } = await join();
    await spend(token, 20);
    await saveSettings({ ...(await getSettings()), monthlyBudgetUsd: 10 });
    await checkSpendAlerts(NOW);
    expect(await titles()).toContain('Monthly budget reached');
  });
});

describe('other alerts', () => {
  it('a workstation over its own limit is named', async () => {
    const { deviceId, token } = await join('RECEPTION');
    const other = await join('SALES');
    await updateDevice(deviceId, { monthlyLimitUsd: 10 }, 'admin', NOW);
    await spend(other.token, 50);
    expect(await titles()).toEqual([]);

    await spend(token, 12);
    const [alert] = (await listAlerts()).open;
    expect(alert.title).toBe('RECEPTION reached its monthly limit');
    expect(alert.device_id).toBe(deviceId);
  });

  it('a high day alerts once that day, and again on another day', async () => {
    const { token } = await join();
    await saveSettings({ ...(await getSettings()), dailyAlertUsd: 5 });
    await spend(token, 3);
    expect(await titles()).toEqual([]);
    await spend(token, 3);
    await spend(token, 3);
    expect(await titles()).toEqual(['High spending today']);
    await spend(token, 6, NOW + 24 * 3_600_000);
    expect(await titles()).toEqual(['High spending today', 'High spending today']);
  });

  it('warns about the pace, but not in the first days of a month or when turned off', async () => {
    const { token } = await join();
    await saveSettings({ ...(await getSettings()), monthlyBudgetUsd: 100 });
    // 2 November: $10 so far is on pace for $150, but too early to say
    await spend(token, 10, Date.parse('2026-11-02T12:00:00Z'));
    expect(await titles()).toEqual([]);
    // 3 November: on pace for over $100, with no step reached
    await spend(token, 5, Date.parse('2026-11-03T12:00:00Z'));
    expect(await titles()).toEqual(['On pace to go over the monthly budget']);

    await acknowledgeAlerts(null, 'admin', NOW);
    await saveSettings({ ...(await getSettings()), paceAlert: false });
    await spend(token, 1, Date.parse('2026-12-03T12:00:00Z'));
    await spend(token, 10, Date.parse('2026-12-03T12:00:00Z'));
    expect(await titles()).toEqual([]);
  });

  it('usage sent twice does not check again, acknowledging clears the count and keeps the record', async () => {
    const { token } = await join();
    await saveSettings({ ...(await getSettings()), monthlyBudgetUsd: 10 });
    await spend(token, 11);
    const { open } = await listAlerts();
    expect(open).toHaveLength(1);
    await acknowledgeAlerts(open[0].id, 'admin', NOW);
    const after = await listAlerts();
    expect(after.open).toEqual([]);
    expect(after.past[0].acknowledged_by).toBe('admin');
    await spend(token, 1);
    expect((await listAlerts()).open).toEqual([]); // not raised again this month
  });
});

describe('email', () => {
  const email = () => {
    const send = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', send);
    return send;
  };

  it('nothing is sent without a key or an address, and it still shows here', async () => {
    const send = email();
    const { token } = await join();
    await saveSettings({ ...(await getSettings()), monthlyBudgetUsd: 10, alertEmails: ['a@b.example'] });
    await spend(token, 11);
    expect(send).not.toHaveBeenCalled();
    expect(await titles()).toHaveLength(1);
    expect(await sendTestEmail()).toContain('not set up');

    process.env.RESEND_API_KEY = 'key';
    await saveSettings({ ...(await getSettings()), alertEmails: [] });
    await spend(token, 1);
    expect(send).not.toHaveBeenCalled();
    expect(await sendTestEmail()).toContain('Add an address');
  });

  it('new alerts are emailed once, together', async () => {
    const send = email();
    process.env.RESEND_API_KEY = 'key';
    const { token } = await join();
    await saveSettings({
      ...(await getSettings()),
      monthlyBudgetUsd: 10,
      dailyAlertUsd: 5,
      alertEmails: ['a@b.example', 'c@d.example'],
    });
    await spend(token, 11);
    expect(send).toHaveBeenCalledTimes(1);
    const [url, options] = send.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('https://api.resend.com/emails');
    const body = JSON.parse(String(options.body));
    expect(body.to).toEqual(['a@b.example', 'c@d.example']);
    expect(body.subject).toBe('HireAce: 2 spending alerts');
    expect(body.text).toContain('Monthly budget reached');

    await spend(token, 1);
    expect(send).toHaveBeenCalledTimes(1);
    expect((await listAlerts()).open.every((alert) => alert.emailed_at)).toBe(true);
  });

  it('a failed email says why, is tried again with the next usage, and never stops the check-in', async () => {
    const send = vi.fn(async () => new Response(JSON.stringify({ message: 'Domain not verified' }), { status: 403 }));
    vi.stubGlobal('fetch', send);
    vi.spyOn(console, 'error').mockImplementation(() => {});
    process.env.RESEND_API_KEY = 'key';
    const { token } = await join();
    await saveSettings({ ...(await getSettings()), monthlyBudgetUsd: 10, alertEmails: ['a@b.example'] });

    expect(await spend(token, 11)).toMatchObject({ active: true });
    expect((await listAlerts()).open[0].email_error).toBe('Domain not verified');
    expect(await sendTestEmail()).toBe('Domain not verified');

    send.mockImplementation(async () => new Response('{}', { status: 200 }));
    await spend(token, 1);
    const [alert] = (await listAlerts()).open;
    expect(alert.emailed_at).toBeTruthy();
    expect(alert.email_error).toBe('');
  });
});

describe('settings', () => {
  it('refuses bad alert settings', async () => {
    const errors = await saveSettings({
      ...(await getSettings()),
      alertPercents: [0, 120],
      dailyAlertUsd: -1,
      alertEmails: ['not an address'],
    });
    expect(Object.keys(errors).sort()).toEqual(['alertEmails', 'alertPercents', 'dailyAlertUsd']);
  });
});

describe('history', () => {
  it('pages of days, with what was spent per workstation and model', async () => {
    const { token } = await join('PC-1');
    const other = await join('PC-2');
    await spend(token, 10);
    await spend(other.token, 2, NOW, 'gpt-realtime-2.1-mini');
    await spend(token, 4, NOW - 8 * 24 * 3_600_000);

    const week = await usageHistory(7, 0, NOW);
    expect(week.days).toHaveLength(7);
    expect(week.days.at(-1)).toBe('2026-11-15');
    expect(week.hasEarlier).toBe(true);
    expect(week.rows.map((row) => row.name).sort()).toEqual(['PC-1', 'PC-2']);
    expect(week.rows.find((row) => row.name === 'PC-1')).toMatchObject({ responses: 3 });
    expect(week.rows.find((row) => row.name === 'PC-2')?.model).toBe('gpt-realtime-2.1-mini');

    const before = await usageHistory(7, 1, NOW);
    expect(before.days.at(-1)).toBe('2026-11-08');
    expect(before.rows).toHaveLength(1);
    expect(before.hasEarlier).toBe(false);
  });

  it('adds up months and Monday-to-Sunday weeks, leaving out empty ones', async () => {
    const { token } = await join();
    await saveSettings({ ...(await getSettings()), monthlyBudgetUsd: 100 });
    await spend(token, 10, Date.parse('2026-11-15T12:00:00Z')); // a Sunday
    await spend(token, 5, Date.parse('2026-11-09T12:00:00Z')); // that week's Monday
    await spend(token, 7, Date.parse('2026-10-20T12:00:00Z'));

    const { months, weeks } = await spendPeriods(NOW);
    expect(months.map((row) => row.label)).toEqual(['November 2026', 'October 2026']);
    expect(months[0].cost).toBeCloseTo(15);
    expect(months[0].percentOfBudget).toBeCloseTo(15);
    expect(months[0].breakdown[0].name).toBe('PC-1');
    expect(weeks[0].label).toBe('9 Nov – 15 Nov');
    expect(weeks[0].cost).toBeCloseTo(15);
    expect(weeks.at(-1)?.cost).toBeCloseTo(7);
  });
});
