import { useEffect, useState } from 'react';

export interface GmailHealth {
  checked: boolean;
  connected: boolean;
  accounts: { browser: string; email: string }[];
}

export interface GmailState {
  health: GmailHealth | null;
  failed: boolean;
}

const CHECK_EVERY_MS = 10_000;
const STARTING: GmailState = { health: null, failed: false };

// One check for everything showing it (the logo's dot and the bar), however many there are
let current = STARTING;
const listeners = new Set<(state: GmailState) => void>();
let timer: ReturnType<typeof setInterval> | undefined;

function publish(next: GmailState) {
  current = next;
  listeners.forEach((listener) => listener(next));
}

/**
 * Every 10 seconds whatever the last answer was, so a Gmail opened or signed in to shows
 * by itself. Not while the panel is minimized (each check costs the PC about a second of
 * work), but at once when it comes back.
 */
async function check() {
  if (document.hidden) return;
  try {
    const res = await fetch('/api/gmail/health', { cache: 'no-store' });
    if (!res.ok) throw new Error(String(res.status));
    publish({ health: await res.json(), failed: false });
  } catch {
    publish({ health: current.health, failed: true });
  }
}

function subscribe(listener: (state: GmailState) => void) {
  listeners.add(listener);
  listener(current);
  if (listeners.size === 1) {
    check();
    timer = setInterval(check, CHECK_EVERY_MS);
    document.addEventListener('visibilitychange', check);
    window.addEventListener('focus', check);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', check);
      window.removeEventListener('focus', check);
    }
  };
}

/** Gmail on this PC. On a phone onThisPc stays false: only the PC can see its own browsers. */
export function useGmailHealth() {
  const [onThisPc, setOnThisPc] = useState(false);
  const [state, setState] = useState<GmailState>(STARTING);

  useEffect(() => {
    if (!['localhost', '127.0.0.1'].includes(window.location.hostname)) return;
    setOnThisPc(true);
    return subscribe(setState);
  }, []);

  return { onThisPc, state };
}
