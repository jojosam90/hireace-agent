'use client';

import { Check, Eye, EyeOff, LoaderCircle } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Logo } from '@/components/shell';
import { initials } from '@/lib/accounts';

const POINTS = [
  ['Every workstation at a glance', 'See which PCs are online and whether HireAce is up on each one.'],
  ['Updates from one place', 'Install the latest version, restart or deactivate, on one PC or all of them.'],
  ['OpenAI spend under control', 'Set a monthly limit and see what each workstation uses.'],
];

interface PublicAccount {
  username: string;
  name: string;
  role: string;
  /** This device logged in as them before: a click is enough */
  remembered: boolean;
  /** This account's password, if the server is set to fill it in */
  prefillPassword?: string;
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
      .then((data: { accounts: PublicAccount[] }) => setAccounts(data.accounts))
      .catch(() => setError('Could not reach the server.'));
  }, []);

  async function signIn(body: Record<string, unknown>) {
    setBusy(true);
    setError('');
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
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

  /** A card logs straight in when the password is known; otherwise it asks for it. */
  function choose(account: PublicAccount) {
    setUsername(account.username);
    setPassword(account.prefillPassword ?? '');
    setError('');
    if (account.prefillPassword) signIn({ username: account.username, password: account.prefillPassword, remember: true });
    else if (account.remembered) signIn({ username: account.username, useRemembered: true });
    else passwordField.current?.focus();
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    signIn({ username, password, remember: true });
  }

  const known = accounts?.some((account) => account.remembered || account.prefillPassword);

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

      <section className="flex flex-1 items-center justify-center px-6 py-10 [@media(max-height:760px)]:py-5">
        <form onSubmit={submit} className="w-full max-w-xl">
          <h2 className="text-3xl font-extrabold tracking-tight">Welcome back</h2>
          <p className="text-muted mt-2">Log in to manage your HireAce workstations.</p>

          <label htmlFor="username" className="mt-6 block font-semibold [@media(max-height:760px)]:mt-4">
            Username
          </label>
          <input
            id="username"
            name="username"
            autoComplete="username"
            required
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            className="bg-field border-line focus:border-brand-500 mt-2 h-12 w-full rounded-xl border px-4 outline-none focus:bg-white"
          />

          <label htmlFor="password" className="mt-4 block font-semibold">
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
            disabled={busy}
            className="bg-brand-600 hover:bg-brand-700 mt-5 flex h-12 w-full items-center justify-center gap-2 rounded-xl font-bold text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy && <LoaderCircle className="size-5 animate-spin" aria-hidden />}
            Log in
          </button>

          <p id="choose-account" className="text-muted mt-6 text-center text-sm [@media(max-height:760px)]:mt-4">
            {accounts?.length === 0
              ? 'No accounts are set up on the server yet.'
              : known
                ? 'Click an account to log in as that person.'
                : 'Click your account, then enter your password.'}
          </p>
          <div
            role="group"
            aria-labelledby="choose-account"
            className="scroll-thin mt-3 grid max-h-[19rem] grid-cols-1 gap-2.5 overflow-y-auto p-0.5 min-[360px]:grid-cols-2 [@media(max-height:760px)]:max-h-[9.5rem]"
          >
            {accounts?.map((account) => {
              const chosen = username === account.username;
              return (
                <button
                  key={account.username}
                  type="button"
                  aria-pressed={chosen}
                  onClick={() => choose(account)}
                  disabled={busy}
                  className={`flex min-w-0 items-center gap-2 rounded-xl border p-2 text-left transition-colors sm:gap-3 sm:p-2.5 ${
                    accounts.length === 1 ? 'min-[360px]:col-span-2' : ''
                  } ${chosen ? 'border-brand-500 bg-brand-50' : 'border-line hover:bg-page bg-white'}`}
                >
                  <span
                    className="text-brand-700 flex size-8 shrink-0 items-center justify-center rounded-full bg-[#ead9ff] text-xs font-bold sm:size-10 sm:text-sm"
                    aria-hidden
                  >
                    {initials(account.name)}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-bold sm:text-base">{account.name}</span>
                    <span className="text-muted block truncate text-xs sm:text-sm">{account.role}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </form>
      </section>
    </main>
  );
}
