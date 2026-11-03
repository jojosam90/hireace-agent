'use client';

import { useEffect, useState } from 'react';
import { useUiLanguage } from '@/lib/i18n';

interface GmailHealth {
  checked: boolean;
  connected: boolean;
  accounts: { browser: string; email: string }[];
}

const CHECK_EVERY_MS = 10_000;

/**
 * A small bar on the PC's panel: is Gmail signed in, in any browser (Chrome, Edge...)?
 * Checked every 10 seconds, at once when the user comes back to the panel, and not
 * while it is minimized (each check costs the PC about a second of work). One box per
 * account found; clicking one goes to that account's open tab. It never opens a browser.
 */
export function GmailHealthBar() {
  const { t } = useUiLanguage();
  const [health, setHealth] = useState<GmailHealth | null>(null);
  const [failed, setFailed] = useState(false);
  // Which box said its tab is gone, until the next check ('' is the box with no address)
  const [notFound, setNotFound] = useState<string | null>(null);
  const [going, setGoing] = useState(false);

  useEffect(() => {
    if (!['localhost', '127.0.0.1'].includes(window.location.hostname)) return;
    let stopped = false;
    const check = async () => {
      if (document.hidden) return;
      try {
        const res = await fetch('/api/gmail/health', { cache: 'no-store' });
        if (!res.ok) throw new Error(String(res.status));
        const next: GmailHealth = await res.json();
        if (!stopped) {
          setHealth(next);
          setFailed(false);
          setNotFound(null);
        }
      } catch {
        if (!stopped) setFailed(true);
      }
    };
    check();
    const timer = setInterval(check, CHECK_EVERY_MS);
    document.addEventListener('visibilitychange', check);
    window.addEventListener('focus', check);
    return () => {
      stopped = true;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', check);
      window.removeEventListener('focus', check);
    };
  }, []);

  if (!health && !failed) return null;

  const goToGmail = async (email: string) => {
    setGoing(true);
    try {
      const res = await fetch('/api/gmail/show', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(email ? { email } : {}),
      });
      setNotFound(!res.ok || (await res.json()).status !== 'done' ? email : null);
    } catch {
      setNotFound(email);
    } finally {
      setGoing(false);
    }
  };

  const connected = !failed && health?.connected;
  const box = 'w-full rounded-xl border px-3 py-2 text-left text-xs';
  const line = (text: string, on: boolean) => (
    <div className="flex items-start gap-2">
      <span
        className={`mt-1 size-2 shrink-0 rounded-full ${on ? 'bg-emerald-500' : 'bg-zinc-400'}`}
        aria-hidden
      />
      <span className="min-w-0 font-medium break-words">{text}</span>
    </div>
  );

  if (!connected) {
    const text = failed || !health?.checked ? t('gmailBarUnknown') : t('gmailBarNotConnected');
    return (
      <div role="status" className={`mt-3 max-w-xs ${box}`} title={text}>
        {line(text, false)}
      </div>
    );
  }

  // Connected, but no address read from any tab: one box for Gmail as a whole
  const accounts = health?.accounts.length ? health.accounts : [{ browser: '', email: '' }];
  return (
    <div className="mt-3 flex w-full max-w-xs flex-col gap-2">
      {accounts.map(({ browser, email }) => {
        const gone = notFound === email;
        const text = gone
          ? t('gmailBarNotFound')
          : email
            ? t('gmailBarConnectedIn', { where: `${browser} · ${email}` })
            : t('gmailBarConnected');
        return (
          <button
            key={`${browser}-${email}`}
            type="button"
            onClick={() => goToGmail(email)}
            disabled={going}
            className={`${box} hover:bg-muted cursor-pointer transition-colors disabled:cursor-wait`}
            title={t('gmailBarGoTo')}
          >
            {line(text, !gone)}
          </button>
        );
      })}
    </div>
  );
}
