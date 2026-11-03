import { scryptSync } from 'node:crypto';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initials, loadAccounts, publicAccounts } from '@/lib/accounts';
import { login } from '@/lib/auth';
import { resetDbForTests } from '@/lib/db';

const hash = (password: string, salt = 'aa') => `${salt}:${scryptSync(password, salt, 64).toString('hex')}`;
const NOW = Date.parse('2026-11-15T12:00:00Z');
const NAMES = ['ADMIN_ACCOUNTS', 'ADMIN_USERNAME', 'ADMIN_PASSWORD_HASH', 'ADMIN_PREFILL_PASSWORD', 'SESSION_SECRET'];

beforeEach(() => {
  process.env.ADMIN_DATA_DIR = 'memory://';
  delete process.env.DATABASE_URL;
  for (const name of NAMES) delete process.env[name];
  process.env.SESSION_SECRET = 'test';
  resetDbForTests();
});

afterEach(() => vi.restoreAllMocks());

const two = () =>
  JSON.stringify([
    { username: 'farah', name: 'Farah Lee', role: 'Manager', passwordHash: hash('farah-password') },
    { username: 'ravi', name: 'Ravi Kumar', role: 'Sales PIC', passwordHash: hash('ravi-password') },
  ]);

describe('accounts', () => {
  it('uses the list when there is one, and the single account otherwise', () => {
    process.env.ADMIN_USERNAME = 'admin';
    process.env.ADMIN_PASSWORD_HASH = hash('admin-password');
    expect(loadAccounts().map((a) => a.name)).toEqual(['Administrator']);
    process.env.ADMIN_ACCOUNTS = two();
    expect(loadAccounts().map((a) => a.name)).toEqual(['Farah Lee', 'Ravi Kumar']);
  });

  it('a broken list falls back instead of locking everyone out', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    process.env.ADMIN_USERNAME = 'admin';
    process.env.ADMIN_PASSWORD_HASH = hash('admin-password');
    process.env.ADMIN_ACCOUNTS = 'not json';
    expect(loadAccounts().map((a) => a.username)).toEqual(['admin']);
  });

  it('the login page never receives a password hash', () => {
    process.env.ADMIN_ACCOUNTS = two();
    expect(JSON.stringify(publicAccounts())).not.toContain('Hash');
    expect(publicAccounts()[0]).toEqual({ username: 'farah', name: 'Farah Lee', role: 'Manager' });
  });

  it('sends no password unless the server is told to, and then only that one', () => {
    process.env.ADMIN_ACCOUNTS = two();
    expect(JSON.stringify(publicAccounts())).not.toContain('prefill');

    process.env.ADMIN_ACCOUNTS = JSON.stringify([
      { username: 'farah', passwordHash: hash('farah-password'), prefillPassword: 'farah-password' },
      { username: 'ravi', passwordHash: hash('ravi-password') },
    ]);
    const [farah, ravi] = publicAccounts();
    expect(farah.prefillPassword).toBe('farah-password');
    expect(ravi.prefillPassword).toBeUndefined();

    delete process.env.ADMIN_ACCOUNTS;
    process.env.ADMIN_USERNAME = 'admin';
    process.env.ADMIN_PASSWORD_HASH = hash('admin-password');
    expect(publicAccounts()[0].prefillPassword).toBeUndefined();
    process.env.ADMIN_PREFILL_PASSWORD = 'admin-password';
    expect(publicAccounts()[0].prefillPassword).toBe('admin-password');
  });

  it('makes initials from the first and last name', () => {
    expect(initials('Mei Ling Wong')).toBe('MW');
    expect(initials('Farah Lee')).toBe('FL');
    expect(initials('Administrator')).toBe('A');
    expect(initials('  ')).toBe('?');
  });
});

describe('signing in', () => {
  it('each person needs their own password', async () => {
    process.env.ADMIN_ACCOUNTS = two();
    expect(await login('farah', 'farah-password', 'a', NOW)).toBe('ok');
    expect(await login('ravi', 'ravi-password', 'a', NOW)).toBe('ok');
    expect(await login('ravi', 'farah-password', 'a', NOW)).toBe('wrong');
    expect(await login('nobody', 'farah-password', 'a', NOW)).toBe('wrong');
    expect(await login('farah', '', 'a', NOW)).toBe('wrong');
  });

  it('the single account still works', async () => {
    process.env.ADMIN_USERNAME = 'admin';
    process.env.ADMIN_PASSWORD_HASH = hash('admin-password');
    expect(await login('admin', 'admin-password', 'a', NOW)).toBe('ok');
  });

  it('five wrong tries still lock that address', async () => {
    process.env.ADMIN_ACCOUNTS = two();
    for (let i = 0; i < 5; i++) expect(await login('farah', 'wrong', 'b', NOW)).toBe('wrong');
    expect(await login('farah', 'farah-password', 'b', NOW)).toBe('locked');
  });

  it('with no accounts or no session secret it says it is not set up', async () => {
    expect(await login('a', 'b', 'c', NOW)).toBe('not_set_up');
    process.env.ADMIN_ACCOUNTS = two();
    delete process.env.SESSION_SECRET;
    expect(await login('farah', 'farah-password', 'c', NOW)).toBe('not_set_up');
  });
});
