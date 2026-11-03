import { scryptSync } from 'node:crypto';
import { SignJWT } from 'jose';
import { beforeEach, describe, expect, it } from 'vitest';
import { rememberedAccounts, signRemembered } from '@/lib/remember';

const hash = (password: string) => `aa:${scryptSync(password, 'aa', 64).toString('hex')}`;

function accounts(farahPassword = 'farah-password') {
  process.env.ADMIN_ACCOUNTS = JSON.stringify([
    { username: 'farah', name: 'Farah Lee', role: 'Manager', passwordHash: hash(farahPassword) },
    { username: 'ravi', name: 'Ravi Kumar', role: 'Sales PIC', passwordHash: hash('ravi-password') },
  ]);
}

beforeEach(() => {
  process.env.SESSION_SECRET = 'test-secret';
  accounts();
});

describe('remembering a device', () => {
  it('vouches only for the accounts that logged in here', async () => {
    const token = await signRemembered(['farah']);
    expect(await rememberedAccounts(token)).toEqual(['farah']);
  });

  it('holds no password or password hash', async () => {
    const token = await signRemembered(['farah']);
    const payload = Buffer.from(token.split('.')[1], 'base64url').toString();
    expect(payload).not.toContain(hash('farah-password'));
    expect(payload).not.toContain('farah-password');
  });

  it('ends for one person when their password changes, and not for the other', async () => {
    const token = await signRemembered(['farah', 'ravi']);
    accounts('a-new-password');
    expect(await rememberedAccounts(token)).toEqual(['ravi']);
  });

  it('ends for everyone with a new secret', async () => {
    const token = await signRemembered(['farah']);
    process.env.SESSION_SECRET = 'another-secret';
    expect(await rememberedAccounts(token)).toEqual([]);
  });

  it('refuses a made-up, altered or expired cookie, and a sign-in cookie used as one', async () => {
    expect(await rememberedAccounts(undefined)).toEqual([]);
    expect(await rememberedAccounts('not-a-token')).toEqual([]);

    const token = await signRemembered(['farah']);
    const [head, , signature] = token.split('.');
    const altered = Buffer.from(JSON.stringify({ sub: 'device', accounts: { ravi: 'x' } })).toString('base64url');
    expect(await rememberedAccounts(`${head}.${altered}.${signature}`)).toEqual([]);

    const key = new TextEncoder().encode('test-secret');
    const expired = await new SignJWT({ accounts: {} })
      .setProtectedHeader({ alg: 'HS256' })
      .setSubject('device')
      .setExpirationTime(Math.floor(Date.now() / 1000) - 60)
      .sign(key);
    expect(await rememberedAccounts(expired)).toEqual([]);

    const session = await new SignJWT({}).setProtectedHeader({ alg: 'HS256' }).setSubject('farah').setExpirationTime('1h').sign(key);
    expect(await rememberedAccounts(session)).toEqual([]);
  });

  it('a removed account is no longer remembered', async () => {
    const token = await signRemembered(['farah', 'ravi']);
    process.env.ADMIN_ACCOUNTS = JSON.stringify([
      { username: 'ravi', name: 'Ravi Kumar', role: 'Sales PIC', passwordHash: hash('ravi-password') },
    ]);
    expect(await rememberedAccounts(token)).toEqual(['ravi']);
  });
});
