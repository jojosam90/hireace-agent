// The real bill from OpenAI's Admin API, day by day and by model. Optional (OPENAI_ADMIN_KEY)
// and asked at most every 15 minutes. It covers the whole OpenAI organization, in days of UTC,
// and OpenAI posts a day's costs some time after the usage: today can be missing or low.

import { getDb } from './db';

const REFRESH = 15 * 60_000;
const DAYS = 31; // a whole month always fits, and OpenAI's limit for one page

export interface BilledDay {
  day: string;
  cost: number;
  models: Record<string, number>;
}

export interface Bill {
  /** This month so far */
  usd: number;
  at: number;
  /** Could not be refreshed just now: these are the last figures read */
  stale: boolean;
  days: BilledDay[];
}

/** "gpt-realtime-2.1 audio, cached input" -> "gpt-realtime-2.1" */
export function modelOf(lineItem: string | null | undefined): string {
  if (!lineItem) return 'Other';
  return lineItem
    .split(',')[0]
    .replace(/\s+(audio|text|image)$/, '')
    .replace(/-\d{4}-\d{2}-\d{2}$/, '')
    .trim();
}

async function readDays(key: string, now: number): Promise<BilledDay[]> {
  const today = Math.floor(now / 86_400_000) * 86_400;
  const start = today - (DAYS - 1) * 86_400;
  const byDay = new Map<string, Record<string, number>>();
  for (let index = 0; index < DAYS; index++) {
    byDay.set(new Date((start + index * 86_400) * 1000).toISOString().slice(0, 10), {});
  }
  let page: string | null = null;
  do {
    const query = new URLSearchParams({ start_time: String(start), bucket_width: '1d', limit: String(DAYS) });
    query.append('group_by', 'line_item');
    if (page) query.set('page', page);
    const res: Response = await fetch(`https://api.openai.com/v1/organization/costs?${query}`, {
      headers: { Authorization: `Bearer ${key}` },
      signal: AbortSignal.timeout(15_000),
    });
    if (!res.ok) throw new Error(`OpenAI answered ${res.status}`);
    const body = (await res.json()) as {
      data: { start_time: number; results: { amount?: { value?: number }; line_item?: string | null }[] }[];
      has_more?: boolean;
      next_page?: string | null;
    };
    for (const bucket of body.data) {
      const models = byDay.get(new Date(bucket.start_time * 1000).toISOString().slice(0, 10));
      if (!models) continue;
      for (const result of bucket.results) {
        const value = Number(result.amount?.value ?? 0);
        if (!value) continue;
        const model = modelOf(result.line_item);
        models[model] = (models[model] ?? 0) + value;
      }
    }
    page = body.has_more ? (body.next_page ?? null) : null;
  } while (page);
  return [...byDay.entries()].map(([day, models]) => ({
    day,
    models,
    cost: Object.values(models).reduce((sum, value) => sum + value, 0),
  }));
}

export async function openaiBill(now = Date.now()): Promise<Bill | null> {
  const key = process.env.OPENAI_ADMIN_KEY;
  if (!key) return null;
  const db = await getDb();
  const month = new Date(now).toISOString().slice(0, 7);
  const [row] = await db.query<{ value: string }>(`SELECT value FROM settings WHERE key = 'openai_bill'`);
  const saved = row ? (JSON.parse(row.value) as { at: number; days: BilledDay[] }) : null;
  const bill = (at: number, days: BilledDay[], stale: boolean): Bill => ({
    at,
    days,
    stale,
    usd: days.filter((item) => item.day.startsWith(month)).reduce((sum, item) => sum + item.cost, 0),
  });
  if (saved && now - saved.at < REFRESH) return bill(saved.at, saved.days, false);

  try {
    const days = await readDays(key, now);
    await db.query(
      `INSERT INTO settings (key, value) VALUES ('openai_bill', $1)
       ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value`,
      [JSON.stringify({ at: now, days })],
    );
    return bill(now, days, false);
  } catch (error) {
    console.error('OpenAI bill could not be read:', error instanceof Error ? error.message : 'unknown error');
    return saved ? bill(saved.at, saved.days, true) : null;
  }
}
