// "Remember me on this device": a signed cookie naming the accounts that logged in here with
// their password, so tapping a card needs no typing. It holds no password. A password change,
// or a new SESSION_SECRET, ends it; another device still has to type the password.

import { createHash } from 'node:crypto';
import { jwtVerify, SignJWT } from 'jose';
import { loadAccounts } from './accounts';

export const DEVICE_COOKIE = 'hireace_device';
export const DEVICE_DAYS = 30;

const secret = () => new TextEncoder().encode(process.env.SESSION_SECRET ?? '');
const fingerprint = (passwordHash: string) => createHash('sha256').update(passwordHash).digest('hex').slice(0, 24);

/** The accounts this device's cookie still vouches for. */
export async function rememberedAccounts(token: string | undefined): Promise<string[]> {
  if (!token || !process.env.SESSION_SECRET) return [];
  try {
    const { payload } = await jwtVerify(token, secret(), { algorithms: ['HS256'], subject: 'device' });
    const saved = (payload.accounts ?? {}) as Record<string, string>;
    return loadAccounts()
      .filter((account) => saved[account.username] === fingerprint(account.passwordHash))
      .map((account) => account.username);
  } catch {
    return [];
  }
}

/** A new cookie for these accounts, for another 30 days. */
export async function signRemembered(usernames: string[]): Promise<string> {
  const accounts = Object.fromEntries(
    loadAccounts()
      .filter((account) => usernames.includes(account.username))
      .map((account) => [account.username, fingerprint(account.passwordHash)]),
  );
  return new SignJWT({ accounts })
    .setProtectedHeader({ alg: 'HS256' })
    .setSubject('device')
    .setIssuedAt()
    .setExpirationTime(`${DEVICE_DAYS}d`)
    .sign(secret());
}
