'use client';

import { Check, Eye, EyeOff, LoaderCircle } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Logo } from '@/components/shell';
import { initials } from '@/lib/accounts';
import { SESSION_DAYS } from '@/lib/session';

const POINTS = [
  ['Every workstation at a glance', 'See which PCs are online and whether HireAce is up on each one.'],
  ['Updates from one place', 'Install the latest version, restart or deactivate, on one PC or all of them.'],
  ['OpenAI spend under control', 'Set a monthly limit and see what each workstation uses.'],
];

interface PublicAccount {
  username: string;
  name: string;
  role: string;
}

export default function LoginPage() {
  const [accounts, setAccounts] = useState<PublicAccount[] | null>(null);
  const passwordField = useRef<HTMLInputElement>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('/api/auth/accounts', { cache: 'no-store' })
      .then((res) => res.json())
      .then((data: { accounts: PublicAccount[] }) => {
        setAccounts(data.accounts);
        if (data.accounts.length === 1) setUsername(data.accounts[0].username);
      })
      .catch(() => setError('Could not reach the server.'));
  }, []);

  function choose(account: PublicAccount) {
    setUsername(account.username);
    setError('');
    passwordField.current?.focus();
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (res.ok) {
        window.location.href = '/';
        return;
      }
      setError((await res.json()).error ?? 'Could not sign in.');
    } catch {
      setError('Could not reach the server.');
    }
    setBusy(false);
  }

  return (
    <main className="flex min-h-dvh flex-col bg-white lg:flex-row">
      <section className="brand-gradient px-6 py-6 text-white lg:flex lg:w-[53%] lg:flex-col lg:px-14 lg:py-10">
        <Logo />
        <div className="hidden flex-1 flex-col justify-center lg:flex">
          <h1 className="max-w-xl text-5xl leading-tight font-extrabold tracking-tight">
            Every HireAce agent, from one portal.
          </h1>
          <p className="mt-5 max-w-lg text-xl text-white/85">
            Health, updates and OpenAI usage for all your workstations.
          </p>
          <ul className="mt-9 space-y-6">
            {POINTS.map(([title, text]) => (
              <li key={title} className="flex gap-4">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-white/20">
                  <Check className="size-4" aria-hidden />
                </span>
                <span>
                  <span className="block text-lg font-bold">{title}</span>
                  <span className="text-white/80">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className="hidden text-xs text-white/70 lg:block">HireAce by FynixTech</p>
      </section>

      <section className="flex flex-1 items-center justify-center px-6 py-12 [@media(max-height:720px)]:py-5">
        <form onSubmit={submit} className="w-full max-w-xl">
          <h2 className="text-4xl font-extrabold tracking-tight">Welcome back</h2>
          <p className="text-muted mt-4">Log in to manage your HireAce workstations.</p>

          <p id="choose-account" className="mt-8 font-semibold [@media(max-height:720px)]:mt-4">
            Choose your account
          </p>
          {accounts?.length === 0 && (
            <p className="text-muted mt-2 text-sm">No accounts are set up on the server yet.</p>
          )}
          <div
            role="group"
            aria-labelledby="choose-account"
            className="scroll-thin mt-2 grid max-h-72 grid-cols-1 gap-2 overflow-y-auto p-0.5 min-[360px]:grid-cols-2 [@media(max-height:720px)]:max-h-36"
          >
            {accounts?.map((account) => {
              const chosen = username === account.username;
              return (
                <button
                  key={account.username}
                  type="button"
                  aria-pressed={chosen}
                  onClick={() => choose(account)}
                  className={`flex min-w-0 items-center gap-2.5 rounded-xl border p-2.5 text-left transition-colors ${
                    accounts.length === 1 ? 'min-[360px]:col-span-2' : ''
                  } ${chosen ? 'border-brand-500 bg-brand-50' : 'border-line hover:bg-page bg-white'}`}
                >
                  <span
                    className="text-brand-700 flex size-10 shrink-0 items-center justify-center rounded-full bg-[#ead9ff] text-sm font-bold"
                    aria-hidden
                  >
                    {initials(account.name)}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-bold">{account.name}</span>
                    <span className="text-muted block truncate text-sm">{account.role}</span>
                  </span>
                </button>
              );
            })}
          </div>
          {/* For password managers: which account this password belongs to */}
          <input type="text" name="username" autoComplete="username" value={username} readOnly tabIndex={-1} aria-hidden className="sr-only" />

          <label htmlFor="password" className="mt-5 block font-semibold">
            Password
          </label>
          <div className="relative mt-2">
            <input
              id="password"
              ref={passwordField}
              type={show ? 'text' : 'password'}
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="bg-field border-line focus:border-brand-500 h-12 w-full rounded-xl border pr-12 pl-4 outline-none focus:bg-white"
            />
            <button
              type="button"
              onClick={() => setShow(!show)}
              aria-label={show ? 'Hide the password' : 'Show the password'}
              className="text-muted absolute top-0 right-0 flex size-12 items-center justify-center"
            >
              {show ? <EyeOff className="size-5" /> : <Eye className="size-5" />}
            </button>
          </div>

          {error && (
            <p role="alert" className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy || !username}
            className="bg-brand-600 hover:bg-brand-700 mt-8 flex h-14 w-full items-center justify-center gap-2 rounded-xl text-lg font-bold text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy && <LoaderCircle className="size-5 animate-spin" aria-hidden />}
            {username || !accounts?.length ? 'Log in' : 'Choose your account first'}
          </button>
          <p className="text-muted mt-5 text-center text-sm">
            Your session stays signed in for {SESSION_DAYS} days on this device.
          </p>
        </form>
      </section>
    </main>
  );
}
