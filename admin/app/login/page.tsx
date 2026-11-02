'use client';

import { Check, Eye, EyeOff, LoaderCircle } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Logo } from '@/components/shell';

const POINTS = [
  ['Every workstation at a glance', 'See which PCs are online and whether HireAce is up on each one.'],
  ['Updates from one place', 'Install the latest version, restart or deactivate, on one PC or all of them.'],
  ['OpenAI spend under control', 'Set a monthly limit and see what each workstation uses.'],
];

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

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

      <section className="flex flex-1 items-center justify-center px-6 py-12">
        <form onSubmit={submit} className="w-full max-w-md">
          <h2 className="text-3xl font-extrabold tracking-tight">Welcome back</h2>
          <p className="text-muted mt-3">Sign in to manage your HireAce workstations.</p>

          <label htmlFor="username" className="mt-8 block font-semibold">
            Username
          </label>
          <input
            id="username"
            autoComplete="username"
            required
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            className="bg-field border-line focus:border-brand-500 mt-2 h-12 w-full rounded-xl border px-4 outline-none focus:bg-white"
          />

          <label htmlFor="password" className="mt-5 block font-semibold">
            Password
          </label>
          <div className="relative mt-2">
            <input
              id="password"
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
            className="bg-brand-600 hover:bg-brand-700 mt-7 flex h-13 w-full items-center justify-center gap-2 rounded-xl font-bold text-white transition-colors disabled:opacity-70"
          >
            {busy && <LoaderCircle className="size-5 animate-spin" aria-hidden />}
            Sign in
          </button>
        </form>
      </section>
    </main>
  );
}
