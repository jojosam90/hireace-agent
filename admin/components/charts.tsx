'use client';

import { useState } from 'react';
import { compact, shortDay, usd } from '@/lib/format';

function niceMax(value: number): number {
  if (value <= 0) return 1;
  const step = 10 ** Math.floor(Math.log10(value));
  for (const factor of [1, 2, 5, 10]) if (value <= factor * step) return factor * step;
  return 10 * step;
}

/** Spend per day: one series, so the title names it and there is no legend. */
export function DailyBars({ daily }: { daily: { day: string; cost: number }[] }) {
  const [active, setActive] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);
  const top = niceMax(Math.max(...daily.map((row) => row.cost)));
  const shown = active === null ? null : daily[active];

  return (
    <div>
      <div className="mb-2 flex min-h-6 items-center justify-between gap-3 text-sm">
        <span className="text-muted" aria-live="polite">
          {shown ? (
            <>
              {shortDay(shown.day)}: <strong className="text-ink">{usd(shown.cost)}</strong>
            </>
          ) : (
            'Tap or point at a day'
          )}
        </span>
        <button type="button" onClick={() => setAsTable(!asTable)} className="text-brand-700 font-bold">
          {asTable ? 'Show chart' : 'Show table'}
        </button>
      </div>

      {asTable ? (
        <div className="max-h-72 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="text-muted sticky top-0 bg-white text-left">
              <tr>
                <th className="py-1 font-semibold">Day</th>
                <th className="py-1 text-right font-semibold">Estimated spend</th>
              </tr>
            </thead>
            <tbody>
              {[...daily].reverse().map((row) => (
                <tr key={row.day} className="border-line border-t">
                  <td className="py-1.5">{shortDay(row.day)}</td>
                  <td className="py-1.5 text-right font-semibold tabular-nums">{usd(row.cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex gap-2">
          <div className="text-muted flex h-44 w-10 shrink-0 flex-col justify-between text-right text-xs tabular-nums">
            <span>{usd(top)}</span>
            <span>{usd(top / 2)}</span>
            <span>$0</span>
          </div>
          <div className="min-w-0 flex-1">
            <div className="relative h-44" onPointerLeave={() => setActive(null)}>
              <div className="border-line pointer-events-none absolute inset-0 border-t border-b" />
              <div className="border-line pointer-events-none absolute inset-x-0 top-1/2 border-t" />
              <div className="absolute inset-0 flex items-stretch gap-0.5">
                {daily.map((row, index) => (
                  <button
                    key={row.day}
                    type="button"
                    aria-label={`${shortDay(row.day)}: ${usd(row.cost)}`}
                    onPointerEnter={() => setActive(index)}
                    onFocus={() => setActive(index)}
                    onClick={() => setActive(index)}
                    className={`flex min-w-0 flex-1 items-end justify-center rounded-t-sm ${active === index ? 'bg-brand-50' : ''}`}
                  >
                    <span
                      className="bg-brand-600 block w-full max-w-6 rounded-t"
                      style={{ height: row.cost > 0 ? `max(2px, ${(row.cost / top) * 100}%)` : 0 }}
                    />
                  </button>
                ))}
              </div>
            </div>
            <div className="text-muted mt-1 flex justify-between text-xs">
              <span>{shortDay(daily[0].day)}</span>
              <span>{shortDay(daily[daily.length - 1].day)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** Workstations ranked by spend, with the value at the tip. */
export function RankBars({ rows }: { rows: { id: string; name: string; cost: number; limit: number | null }[] }) {
  const top = Math.max(...rows.map((row) => Math.max(row.cost, row.limit ?? 0)), 0.01);
  return (
    <ul className="space-y-3">
      {rows.map((row) => (
        <li key={row.id}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="min-w-0 truncate font-semibold">{row.name}</span>
            <span className="shrink-0 font-bold tabular-nums">
              {usd(row.cost)}
              {row.limit !== null && <span className="text-muted font-semibold"> of {usd(row.limit)}</span>}
            </span>
          </div>
          <div className="mt-1 h-3 rounded-r">
            <div
              className={`h-full max-h-3 rounded-r ${row.limit !== null && row.cost >= row.limit ? 'bg-red-600' : 'bg-brand-600'}`}
              style={{ width: `max(2px, ${(row.cost / top) * 100}%)` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function TokenTable({ tokens }: { tokens: Record<string, number> }) {
  const rows: [string, number][] = [
    ['Audio in', tokens.inAudio],
    ['Audio out', tokens.outAudio],
    ['Text in', tokens.inText],
    ['Text out', tokens.outText],
    ['Images in', tokens.inImage],
    ['Cached (cheaper)', tokens.cached],
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {rows.map(([name, value]) => (
        <div key={name} className="bg-page rounded-xl px-3 py-2">
          <dt className="text-muted text-xs font-semibold">{name}</dt>
          <dd className="text-lg font-extrabold tabular-nums">{compact(value)}</dd>
        </div>
      ))}
    </dl>
  );
}
