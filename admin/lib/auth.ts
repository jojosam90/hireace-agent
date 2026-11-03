import { scryptSync, timingSafeEqual } from 'node:crypto';
import { cookies } from 'next/headers';
import { loadAccounts } from './accounts';
import { getDb } from './db';
import { SESSION_COOKIE, verifySession } from './session';

const WINDOW = 15 * 60_000;
const MAX_FAILURES = 5;

function passwordMatches(password: string, hash: string): boolean {
  const [salt, expected] = hash.split(':');
  if (!salt || !expected) return false;
  const actual = scryptSync(password, salt, 64);
  const wanted = Buffer.from(expected, 'hex');
  return wanted.length === actual.length && timingSafeEqual(actual, wanted);
}

export type LoginResult = 'ok' | 'wrong' | 'locked' | 'not_set_up';

/** Five wrong tries lock that address out for 15 minutes. */
export async function login(
  username: string,
  password: string,
  address: string,
  now = Date.now(),
): Promise<LoginResult> {
  const accounts = loadAccounts();
  if (!accounts.length || !process.env.SESSION_SECRET) return 'not_set_up';
  const db = await getDb();
  await db.query(`DELETE FROM login_failures WHERE at < $1`, [now - WINDOW]);
  const [row] = await db.query<{ n: number }>(`SELECT COUNT(*) AS n FROM login_failures WHERE key = $1`, [address]);
  if (Number(row.n) >= MAX_FAILURES) return 'locked';
  const account = accounts.find((item) => item.username === username);
  // The same work for an unknown name, so the time taken does not tell which names exist
  const right = passwordMatches(password, account?.passwordHash ?? accounts[0].passwordHash) && Boolean(account);
  if (!right) {
    await db.query(`INSERT INTO login_failures (key, at) VALUES ($1, $2)`, [address, now]);
    return 'wrong';
  }
  await db.query(`DELETE FROM login_failures WHERE key = $1`, [address]);
  return 'ok';
}

/** Who is signed in; route handlers are behind middleware.ts, this names them in the log. */
export async function currentAdmin(): Promise<string> {
  const store = await cookies();
  return (await verifySession(store.get(SESSION_COOKIE)?.value)) ?? 'unknown';
}
