// Spending alerts: raised when usage arrives or the limits change, each one once, shown on
// the portal and emailed if email is set up. They only tell: refusing calls is the
// separate "At the limit" setting.

import { randomUUID } from 'node:crypto';
import { getDb } from './db';
import { getSettings } from './settings';

const PACE_FROM_DAY = 3; // the first days of a month say little about its end
const EMAIL_RETRY_HOURS = 24;

export interface AlertRow {
  id: string;
  scope: string;
  level: number;
  severity: 'warn' | 'critical';
  title: string;
  detail: string;
  device_id: string | null;
  created_at: number;
  acknowledged_at: number | null;
  acknowledged_by: string | null;
  emailed_at: number | null;
  email_error: string;
}

const money = (value: number) => `$${value.toFixed(2)}`;

/** Each scope remembers its highest level: a jump from 40% to 90% is one alert, not two. */
async function raise(
  scope: string,
  level: number,
  severity: AlertRow['severity'],
  title: string,
  detail: string,
  deviceId: string | null,
  now: number,
) {
  const db = await getDb();
  const [row] = await db.query<{ top: number | null }>(`SELECT MAX(level) AS top FROM alerts WHERE scope = $1`, [scope]);
  if (row?.top !== null && row?.top !== undefined && Number(row.top) >= level) return;
  await db.query(
    `INSERT INTO alerts (id, scope, level, severity, title, detail, device_id, created_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8) ON CONFLICT (scope, level) DO NOTHING`,
    [randomUUID(), scope, level, severity, title, detail, deviceId, now],
  );
}

/** The highest step this share of a limit has passed. Reaching the limit always counts. */
function stepReached(spent: number, limit: number, steps: number[]): number | null {
  const percent = (spent / limit) * 100;
  const passed = [...steps, 100].filter((step) => percent >= step);
  return passed.length ? Math.max(...passed) : null;
}

export async function checkSpendAlerts(now = Date.now()) {
  const db = await getDb();
  const settings = await getSettings();
  const date = new Date(now);
  const month = date.toISOString().slice(0, 7);
  const today = date.toISOString().slice(0, 10);
  const rows = await db.query<{ id: string; name: string; own: number | null; cost: number }>(
    `SELECT d.id, COALESCE(NULLIF(d.label, ''), d.hostname) AS name, d.monthly_limit_usd AS own, SUM(u.cost_usd) AS cost
     FROM usage_daily u JOIN devices d ON d.id = u.device_id WHERE u.day LIKE $1 GROUP BY d.id, d.label, d.hostname, d.monthly_limit_usd`,
    [`${month}-%`],
  );
  const monthCost = rows.reduce((sum, row) => sum + Number(row.cost), 0);

  const budget = settings.monthlyBudgetUsd;
  if (budget !== null) {
    const step = stepReached(monthCost, budget, settings.alertPercents);
    if (step !== null) {
      await raise(
        // With the limit in it: reaching a raised budget alerts again
        `budget:${month}:${budget}`,
        step,
        step >= 100 ? 'critical' : 'warn',
        step >= 100 ? 'Monthly budget reached' : `${step}% of the monthly budget used`,
        `${money(monthCost)} of ${money(budget)} (estimate). ${
          step >= 100 && settings.atLimit === 'block' ? 'New calls are refused.' : 'Calls continue.'
        }`,
        null,
        now,
      );
    }
    const daysInMonth = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).getUTCDate();
    const pace = (monthCost / date.getUTCDate()) * daysInMonth;
    if (settings.paceAlert && date.getUTCDate() >= PACE_FROM_DAY && pace > budget && monthCost < budget) {
      await raise(
        `pace:${month}:${budget}`,
        100,
        'warn',
        'On pace to go over the monthly budget',
        `On pace for ${money(pace)} against a budget of ${money(budget)}, with ${money(monthCost)} used so far.`,
        null,
        now,
      );
    }
  }

  for (const row of rows) {
    const limit = row.own ?? settings.deviceMonthlyUsd;
    if (limit === null) continue;
    const step = stepReached(Number(row.cost), limit, settings.alertPercents);
    if (step === null) continue;
    await raise(
      `device:${row.id}:${month}:${limit}`,
      step,
      step >= 100 ? 'critical' : 'warn',
      step >= 100 ? `${row.name} reached its monthly limit` : `${row.name} used ${step}% of its monthly limit`,
      `${money(Number(row.cost))} of ${money(limit)} (estimate).`,
      row.id,
      now,
    );
  }

  if (settings.dailyAlertUsd !== null) {
    const [day] = await db.query<{ cost: number | null }>(`SELECT SUM(cost_usd) AS cost FROM usage_daily WHERE day = $1`, [today]);
    const dayCost = Number(day?.cost ?? 0);
    if (dayCost >= settings.dailyAlertUsd) {
      await raise(
        `daily:${today}`,
        100,
        'warn',
        'High spending today',
        `${money(dayCost)} today (estimate), above the alert at ${money(settings.dailyAlertUsd)} a day.`,
        null,
        now,
      );
    }
  }

  await emailNewAlerts(now);
}

// --- Email (Resend) --------------------------------------------------------------------

export const emailIsSetUp = () => Boolean(process.env.RESEND_API_KEY);

async function sendEmail(to: string[], subject: string, text: string) {
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from: process.env.ALERT_EMAIL_FROM || 'HireAce Alerts <onboarding@resend.dev>',
      to,
      subject,
      text,
    }),
    signal: AbortSignal.timeout(8000),
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { message?: string };
    throw new Error(body.message || `The email service answered ${res.status}`);
  }
}

/** Alerts not emailed yet, together in one email. Tried again with the next usage, for a day. */
async function emailNewAlerts(now: number) {
  const { alertEmails } = await getSettings();
  if (!emailIsSetUp() || !alertEmails.length) return;
  const db = await getDb();
  const waiting = await db.query<AlertRow>(
    `SELECT * FROM alerts WHERE emailed_at IS NULL AND acknowledged_at IS NULL AND created_at > $1 ORDER BY created_at`,
    [now - EMAIL_RETRY_HOURS * 3_600_000],
  );
  if (!waiting.length) return;
  const subject = waiting.length === 1 ? `HireAce: ${waiting[0].title}` : `HireAce: ${waiting.length} spending alerts`;
  const body = waiting.map((alert) => `${alert.title}\n${alert.detail}`).join('\n\n');
  try {
    await sendEmail(alertEmails, subject, body);
    for (const alert of waiting) {
      await db.query(`UPDATE alerts SET emailed_at = $2, email_error = '' WHERE id = $1`, [alert.id, now]);
    }
  } catch (error) {
    const reason = error instanceof Error ? error.message : 'Could not send';
    console.error('Alert email failed:', reason);
    for (const alert of waiting) {
      await db.query(`UPDATE alerts SET email_error = $2 WHERE id = $1`, [alert.id, reason.slice(0, 300)]);
    }
  }
}

export async function sendTestEmail(): Promise<string | null> {
  const { alertEmails } = await getSettings();
  if (!emailIsSetUp()) return 'Email is not set up on the server (RESEND_API_KEY).';
  if (!alertEmails.length) return 'Add an address and save first.';
  try {
    await sendEmail(alertEmails, 'HireAce: test alert', 'Spending alerts from the HireAce admin portal will arrive like this.');
    return null;
  } catch (error) {
    return error instanceof Error ? error.message : 'Could not send.';
  }
}

// --- What the portal shows -------------------------------------------------------------

export async function listAlerts() {
  const db = await getDb();
  const open = await db.query<AlertRow>(
    `SELECT * FROM alerts WHERE acknowledged_at IS NULL ORDER BY created_at DESC LIMIT 50`,
  );
  const past = await db.query<AlertRow>(
    `SELECT * FROM alerts WHERE acknowledged_at IS NOT NULL ORDER BY created_at DESC LIMIT 20`,
  );
  return { open, past, emailReady: emailIsSetUp() };
}

export async function acknowledgeAlerts(id: string | null, admin: string, now = Date.now()) {
  const db = await getDb();
  await db.query(
    `UPDATE alerts SET acknowledged_at = $1, acknowledged_by = $2
     WHERE acknowledged_at IS NULL AND ($3::text IS NULL OR id = $3)`,
    [now, admin, id],
  );
}
