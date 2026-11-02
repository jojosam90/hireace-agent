import { getDb } from './db';

export interface Prices {
  inText: number;
  cachedText: number;
  inAudio: number;
  cachedAudio: number;
  inImage: number;
  outText: number;
  outAudio: number;
}

export interface PortalSettings {
  /** Month's spend for all workstations together; null: no limit */
  monthlyBudgetUsd: number | null;
  /** Warn at this share of a limit */
  warnPercent: number;
  /** Each workstation's month, unless it has its own limit; null: no limit */
  deviceMonthlyUsd: number | null;
  /** warn: only shown here. block: new calls are refused until the month ends or it is raised */
  atLimit: 'warn' | 'block';
  /** How often workstations check in */
  heartbeatSeconds: number;
  /** Silent this long: shown as offline */
  offlineAfterSeconds: number;
  /** US dollars per 1M tokens */
  prices: Prices;
}

// gpt-realtime-2.1 in November 2026 (image input is a guess); editable under Usage
export const DEFAULT_SETTINGS: PortalSettings = {
  monthlyBudgetUsd: null,
  warnPercent: 80,
  deviceMonthlyUsd: null,
  atLimit: 'warn',
  heartbeatSeconds: 60,
  offlineAfterSeconds: 180,
  prices: {
    inText: 4,
    cachedText: 0.4,
    inAudio: 32,
    cachedAudio: 0.4,
    inImage: 5,
    outText: 24,
    outAudio: 64,
  },
};

export async function getSettings(): Promise<PortalSettings> {
  const db = await getDb();
  const rows = await db.query<{ value: string }>(`SELECT value FROM settings WHERE key = 'portal'`);
  if (!rows.length) return DEFAULT_SETTINGS;
  const saved = JSON.parse(rows[0].value) as Partial<PortalSettings>;
  return { ...DEFAULT_SETTINGS, ...saved, prices: { ...DEFAULT_SETTINGS.prices, ...saved.prices } };
}

const isPrice = (value: unknown) => typeof value === 'number' && Number.isFinite(value) && value >= 0;
const limit = (value: unknown) => value === null || (isPrice(value) && (value as number) > 0);

/** Returns what is wrong with the settings, by field; empty when they were saved. */
export async function saveSettings(input: PortalSettings): Promise<Record<string, string>> {
  const errors: Record<string, string> = {};
  if (!limit(input.monthlyBudgetUsd)) errors.monthlyBudgetUsd = 'Enter an amount above 0, or leave it empty.';
  if (!limit(input.deviceMonthlyUsd)) errors.deviceMonthlyUsd = 'Enter an amount above 0, or leave it empty.';
  if (!(input.warnPercent >= 1 && input.warnPercent <= 100)) errors.warnPercent = 'Enter a number from 1 to 100.';
  if (input.atLimit !== 'warn' && input.atLimit !== 'block') errors.atLimit = 'Choose what happens at the limit.';
  if (!(input.heartbeatSeconds >= 30 && input.heartbeatSeconds <= 900)) {
    errors.heartbeatSeconds = 'Enter 30 to 900 seconds.';
  }
  if (!(input.offlineAfterSeconds >= input.heartbeatSeconds * 2)) {
    errors.offlineAfterSeconds = 'Allow at least two missed check-ins.';
  }
  for (const key of Object.keys(DEFAULT_SETTINGS.prices) as (keyof Prices)[]) {
    if (!isPrice(input.prices?.[key])) errors[`prices.${key}`] = 'Enter a price of 0 or more.';
  }
  if (Object.keys(errors).length) return errors;

  const clean: PortalSettings = {
    monthlyBudgetUsd: input.monthlyBudgetUsd,
    warnPercent: input.warnPercent,
    deviceMonthlyUsd: input.deviceMonthlyUsd,
    atLimit: input.atLimit,
    heartbeatSeconds: input.heartbeatSeconds,
    offlineAfterSeconds: input.offlineAfterSeconds,
    prices: input.prices,
  };
  const db = await getDb();
  await db.query(
    `INSERT INTO settings (key, value) VALUES ('portal', $1)
     ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value`,
    [JSON.stringify(clean)],
  );
  return {};
}
