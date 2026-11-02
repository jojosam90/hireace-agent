'use client';

import { useCallback, useEffect, useState } from 'react';

export async function call<T = Record<string, unknown>>(url: string, method = 'GET', body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    cache: 'no-store',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401) window.location.href = '/login';
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error ?? 'The server could not do that.');
  return data as T;
}

/** Reads a page's data, and again every 15 seconds while the page is on screen. */
export function usePoll<T>(url: string, everyMs = 15_000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');

  const reload = useCallback(async () => {
    try {
      setData(await call<T>(url));
      setError('');
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Could not reach the server.');
    }
  }, [url]);

  useEffect(() => {
    reload();
    const timer = setInterval(() => {
      if (!document.hidden) reload();
    }, everyMs);
    document.addEventListener('visibilitychange', reload);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', reload);
    };
  }, [reload, everyMs]);

  return { data, error, reload };
}
