// The real bill from OpenAI's Admin API, for comparing with HireAce's own estimate.
// Optional (OPENAI_ADMIN_KEY) and asked at most once an hour.

import { getDb } from './db';

const REFRESH = 3_600_000;

interface Saved {
  month: string;
  at: number;
  usd: number;
}

export async function billedThisMonth(now = Date.now()): Promise<{ usd: number; at: number } | null> {
  const key = process.env.OPENAI_ADMIN_KEY;
  if (!key) return null;
  const db = await getDb();
  const month = new Date(now).toISOString().slice(0, 7);
  const [row] = await db.query<{ value: string }>(`SELECT value FROM settings WHERE key = 'openai_billed'`);
  const saved = row ? (JSON.parse(row.value) as Saved) : null;
  if (saved && saved.month === month && now - saved.at < REFRESH) return saved;

  try {
    const start = Math.floor(Date.parse(`${month}-01T00:00:00Z`) / 1000);
    let usd = 0;
    let page: string | null = null;
    do {
      const query = new URLSearchParams({ start_time: String(start), bucket_width: '1d', limit: '31' });
      if (page) query.set('page', page);
      const res: Response = await fetch(`https://api.openai.com/v1/organization/costs?${query}`, {
        headers: { Authorization: `Bearer ${key}` },
      });
      if (!res.ok) throw new Error(`OpenAI answered ${res.status}`);
      const body = (await res.json()) as {
        data: { results: { amount: { value: number } }[] }[];
        has_more?: boolean;
        next_page?: string | null;
      };
      for (const bucket of body.data) {
        for (const result of bucket.results) usd += Number(result.amount?.value ?? 0);
      }
      page = body.has_more ? (body.next_page ?? null) : null;
    } while (page);
    const fresh: Saved = { month, at: now, usd };
    await db.query(
      `INSERT INTO settings (key, value) VALUES ('openai_billed', $1)
       ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value`,
      [JSON.stringify(fresh)],
    );
    return fresh;
  } catch (error) {
    console.error('OpenAI bill could not be read:', error);
    return saved && saved.month === month ? saved : null;
  }
}
