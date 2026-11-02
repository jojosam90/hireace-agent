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
 * while it is minimized (each check costs the PC about a second of work). Clicking it
 * goes to the Gmail already open; it never opens a browser.
 */
export function GmailHealthBar() {
  const { t } = useUiLanguage();
  const [health, setHealth] = useState<GmailHealth | null>(null);
  const [failed, setFailed] = useState(false);
  const [notFound, setNotFound] = useState(false);
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
          setNotFound(false);
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

  const goToGmail = async () => {
    setGoing(true);
    try {
      const res = await fetch('/api/gmail/show', { method: 'POST' });
      setNotFound(!res.ok || (await res.json()).status !== 'done');
    } catch {
      setNotFound(true);
    } finally {
      setGoing(false);
    }
  };

  const connected = !failed && health?.connected;
  const where = (health?.accounts ?? []).map((a) => `${a.browser} · ${a.email}`).join(', ');
  const text = notFound
    ? t('gmailBarNotFound')
    : connected
      ? where
        ? t('gmailBarConnectedIn', { where })
        : t('gmailBarConnected')
      : failed || !health?.checked
        ? t('gmailBarUnknown')
        : t('gmailBarNotConnected');
  const box = 'mt-3 w-full max-w-xs rounded-xl border px-3 py-2 text-left text-xs';
  const content = (
    <div className="flex items-start gap-2">
      <span
        className={`mt-1 size-2 shrink-0 rounded-full ${connected && !notFound ? 'bg-emerald-500' : 'bg-zinc-400'}`}
        aria-hidden
      />
      <span className="min-w-0 font-medium break-words">{text}</span>
    </div>
  );

  if (!connected) {
    return (
      <div role="status" className={box} title={text}>
        {content}
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={goToGmail}
      disabled={going}
      className={`${box} hover:bg-muted cursor-pointer transition-colors disabled:cursor-wait`}
      title={t('gmailBarGoTo')}
    >
      {content}
    </button>
  );
}
