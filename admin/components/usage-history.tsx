'use client';

import { ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Card, CardTitle, Loading, Problem } from '@/components/ui';
import { usePoll } from '@/lib/client';
import { compact, shortDay, usd } from '@/lib/format';
import type { PeriodRow, UsageHistoryData } from '@/lib/types';

// Fixed order, validated for colour blindness against a white card (dataviz validator).
// Eight at most: anything more folds into Other.
const COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
const OTHER_COLOR = '#8a8795';
const MAX_NAMED = 7;
const MAX_LINES = 4; // more lines than this cross into a tangle

type GroupBy = 'workstation' | 'model';

interface Series {
  key: string;
  color: string;
  cost: number;
  responses: number;
}

function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: [T, string][];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="bg-brand-50 inline-flex rounded-xl p-1">
      {options.map(([option, text]) => (
        <button
          key={option}
          type="button"
          aria-pressed={value === option}
          onClick={() => onChange(option)}
          className={`rounded-lg px-3 py-1 text-sm font-bold transition-colors ${
            value === option ? 'text-brand-700 bg-white shadow-sm' : 'text-muted'
          }`}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

function niceMax(value: number): number {
  if (value <= 0) return 1;
  const step = 10 ** Math.floor(Math.log10(value));
  for (const factor of [1, 2, 5, 10]) if (value <= factor * step) return factor * step;
  return 10 * step;
}

const percentText = (share: number) => (share > 0 && share < 0.1 ? '<0.1%' : `${share.toFixed(1)}%`);

function XAxis({ days }: { days: string[] }) {
  const middle = days[Math.floor(days.length / 2)];
  return (
    <div className="text-muted mt-1 flex justify-between text-xs">
      <span>{shortDay(days[0])}</span>
      <span>{shortDay(middle)}</span>
      <span>{shortDay(days[days.length - 1])}</span>
    </div>
  );
}

function StackedBars({
  days,
  series,
  valueOf,
}: {
  days: string[];
  series: Series[];
  valueOf: (day: string, key: string) => number;
}) {
  const [active, setActive] = useState<number | null>(null);
  const totals = days.map((day) => series.reduce((sum, item) => sum + valueOf(day, item.key), 0));
  const top = niceMax(Math.max(...totals));
  const day = active === null ? null : days[active];

  return (
    <div>
      <p className="text-muted mb-2 min-h-10 text-sm sm:min-h-6" aria-live="polite">
        {day ? (
          <>
            <strong className="text-ink">
              {shortDay(day)}: {usd(totals[active!])}
            </strong>
            {series
              .filter((item) => valueOf(day, item.key) > 0)
              .map((item) => ` · ${item.key} ${usd(valueOf(day, item.key))}`)
              .join('')}
          </>
        ) : (
          'Tap or point at a day'
        )}
      </p>
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
              {days.map((date, index) => (
                <button
                  key={date}
                  type="button"
                  aria-label={`${shortDay(date)}: ${usd(totals[index])}`}
                  onPointerEnter={() => setActive(index)}
                  onFocus={() => setActive(index)}
                  onClick={() => setActive(index)}
                  className={`flex min-w-0 flex-1 flex-col items-center justify-end rounded-t-sm ${active === index ? 'bg-brand-50' : ''}`}
                >
                  <span className="flex w-full max-w-6 flex-col gap-0.5 overflow-hidden rounded-t" style={{ height: `${(totals[index] / top) * 100}%` }}>
                    {[...series].reverse().map((item) =>
                      valueOf(date, item.key) > 0 ? (
                        <span
                          key={item.key}
                          className="block min-h-px w-full"
                          style={{ flexGrow: valueOf(date, item.key), flexBasis: 0, background: item.color }}
                        />
                      ) : null,
                    )}
                  </span>
                </button>
              ))}
            </div>
          </div>
          <XAxis days={days} />
        </div>
      </div>
    </div>
  );
}

function Lines({
  days,
  series,
  valueOf,
}: {
  days: string[];
  series: Series[];
  valueOf: (day: string, key: string) => number;
}) {
  const [active, setActive] = useState<number | null>(null);
  const top = niceMax(Math.max(0, ...days.flatMap((day) => series.map((item) => valueOf(day, item.key)))));
  const x = (index: number) => (days.length === 1 ? 50 : (index / (days.length - 1)) * 100);
  const y = (value: number) => 100 - (value / top) * 100;
  const day = active === null ? null : days[active];

  return (
    <div>
      <p className="text-muted mb-2 min-h-10 text-sm sm:min-h-6" aria-live="polite">
        {day ? (
          <>
            <strong className="text-ink">{shortDay(day)}</strong>
            {series.map((item) => ` · ${item.key} ${compact(valueOf(day, item.key))}`).join('')}
          </>
        ) : (
          'Tap or point at a day'
        )}
      </p>
      <div className="flex gap-2">
        <div className="text-muted flex h-40 w-10 shrink-0 flex-col justify-between text-right text-xs tabular-nums">
          <span>{compact(top)}</span>
          <span>{compact(top / 2)}</span>
          <span>0</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="relative h-40" onPointerLeave={() => setActive(null)}>
            <div className="border-line pointer-events-none absolute inset-0 border-t border-b" />
            <div className="border-line pointer-events-none absolute inset-x-0 top-1/2 border-t" />
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 size-full overflow-visible" aria-hidden>
              {series.map((item) => (
                <polyline
                  key={item.key}
                  fill="none"
                  stroke={item.color}
                  strokeWidth="2"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  vectorEffect="non-scaling-stroke"
                  points={days.map((date, index) => `${x(index)},${y(valueOf(date, item.key))}`).join(' ')}
                />
              ))}
            </svg>
            {active !== null && (
              <>
                <div className="bg-line pointer-events-none absolute inset-y-0 w-px" style={{ left: `${x(active)}%` }} />
                {series.map((item) => (
                  <span
                    key={item.key}
                    className="pointer-events-none absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white"
                    style={{ left: `${x(active)}%`, top: `${y(valueOf(days[active], item.key))}%`, background: item.color }}
                  />
                ))}
              </>
            )}
            {/* Wider than the line: one target per day, across the whole height */}
            <div className="absolute inset-0 flex">
              {days.map((date, index) => (
                <button
                  key={date}
                  type="button"
                  aria-label={`${shortDay(date)}: ${series.map((item) => `${item.key} ${valueOf(date, item.key)}`).join(', ')}`}
                  onPointerEnter={() => setActive(index)}
                  onFocus={() => setActive(index)}
                  onClick={() => setActive(index)}
                  className="min-w-0 flex-1"
                />
              ))}
            </div>
          </div>
          <XAxis days={days} />
        </div>
      </div>
    </div>
  );
}

function PeriodTable({ title, rows, showShare }: { title: string; rows: PeriodRow[]; showShare: boolean }) {
  const [open, setOpen] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, 4);
  return (
    <div className="min-w-0">
      <h3 className="mb-2 font-extrabold">{title}</h3>
      <div className="border-line overflow-hidden rounded-xl border">
        <div className="bg-page text-muted flex justify-between px-3 py-2 text-sm font-semibold">
          <span>Period</span>
          <span>{showShare ? 'Spend · % of budget' : 'Spend'}</span>
        </div>
        {shown.map((row) => {
          const isOpen = open === row.label;
          return (
            <div key={row.label} className="border-line border-t text-sm">
              <button
                type="button"
                aria-expanded={isOpen}
                onClick={() => setOpen(isOpen ? null : row.label)}
                className="hover:bg-page flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left"
              >
                <span className="flex min-w-0 items-center gap-1 font-semibold">
                  {row.label}
                  <ChevronDown className={`text-muted size-4 shrink-0 transition-transform ${isOpen ? 'rotate-180' : ''}`} aria-hidden />
                </span>
                <span className="shrink-0 font-bold tabular-nums">
                  {usd(row.cost)}
                  {showShare && row.percentOfBudget !== null && (
                    <span className="text-muted font-semibold"> · {Math.round(row.percentOfBudget)}%</span>
                  )}
                </span>
              </button>
              {isOpen && (
                <ul className="text-muted space-y-1 px-3 pb-3">
                  {row.breakdown.length === 0 && <li>No usage</li>}
                  {row.breakdown.map((item) => (
                    <li key={item.name} className="flex justify-between gap-3">
                      <span className="min-w-0 truncate">{item.name}</span>
                      <span className="shrink-0 tabular-nums">{usd(item.cost)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
      {rows.length > 4 && (
        <button type="button" onClick={() => setAll(!all)} className="text-brand-700 mt-2 text-sm font-bold">
          {all ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  );
}

export function UsageHistory() {
  const [days, setDays] = useState<7 | 30>(7);
  const [page, setPage] = useState(0);
  const [group, setGroup] = useState<GroupBy>('workstation');
  const [asTable, setAsTable] = useState(false);
  const { data, error } = usePoll<UsageHistoryData>(`/api/admin/usage/history?days=${days}&page=${page}`, 30_000);

  const chart = useMemo(() => {
    if (!data) return null;
    const nameOf = (row: UsageHistoryData['rows'][number]) => (group === 'model' ? row.model : row.name);
    const totals = new Map<string, { cost: number; responses: number }>();
    for (const row of data.rows) {
      const entry = totals.get(nameOf(row)) ?? { cost: 0, responses: 0 };
      entry.cost += row.cost;
      entry.responses += row.responses;
      totals.set(nameOf(row), entry);
    }
    const ranked = [...totals.entries()].sort((a, b) => b[1].cost - a[1].cost);
    const named = ranked.slice(0, MAX_NAMED).map(([key]) => key);
    // Colours follow the name, not the rank: switching 7d and 30d does not repaint a PC
    const series: Series[] = [...named].sort().map((key, index) => ({
      key,
      color: COLORS[index],
      ...totals.get(key)!,
    }));
    const rest = ranked.slice(MAX_NAMED);
    if (rest.length) {
      series.push({
        key: 'Other',
        color: OTHER_COLOR,
        cost: rest.reduce((sum, [, entry]) => sum + entry.cost, 0),
        responses: rest.reduce((sum, [, entry]) => sum + entry.responses, 0),
      });
    }
    const costs = new Map<string, number>();
    const answers = new Map<string, number>();
    for (const row of data.rows) {
      const key = named.includes(nameOf(row)) ? nameOf(row) : 'Other';
      costs.set(`${row.day}|${key}`, (costs.get(`${row.day}|${key}`) ?? 0) + row.cost);
      answers.set(`${row.day}|${key}`, (answers.get(`${row.day}|${key}`) ?? 0) + row.responses);
    }
    const responses = (day: string, key: string) => answers.get(`${day}|${key}`) ?? 0;
    // The busiest keep their colours; the rest are one line
    const busiest = [...series].filter((item) => item.key !== 'Other').sort((a, b) => b.responses - a.responses);
    const drawn = busiest.slice(0, MAX_LINES);
    const merged = series.filter((item) => !drawn.includes(item));
    const lineSeries: Series[] = series.filter((item) => drawn.includes(item));
    if (merged.length) {
      lineSeries.push({
        key: 'Other',
        color: OTHER_COLOR,
        cost: 0,
        responses: merged.reduce((sum, item) => sum + item.responses, 0),
      });
    }
    return {
      series,
      lineSeries,
      lineValue: (day: string, key: string) =>
        key === 'Other' ? merged.reduce((sum, item) => sum + responses(day, item.key), 0) : responses(day, key),
      cost: (day: string, key: string) => costs.get(`${day}|${key}`) ?? 0,
      totalCost: series.reduce((sum, item) => sum + item.cost, 0),
      totalResponses: series.reduce((sum, item) => sum + item.responses, 0),
    };
  }, [data, group]);

  if (!data || !chart) return error ? <Problem>{error}</Problem> : <Loading />;

  const range = `${shortDay(data.days[0])} – ${shortDay(data.days[data.days.length - 1])}, ${data.days[data.days.length - 1].slice(0, 4)}`;

  return (
    <>
      <div className="mt-6 mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-extrabold">Usage history</h2>
          <p className="text-muted text-sm">Estimated spend on the voice model, from what each workstation reports.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Segmented
            label="Days shown"
            value={days}
            options={[[7, '7d'], [30, '30d']]}
            onChange={(value) => {
              setDays(value);
              setPage(0);
            }}
          />
          <Segmented label="Break down by" value={group} options={[['workstation', 'By PC'], ['model', 'By model']]} onChange={setGroup} />
        </div>
      </div>

      <Card>
        <div className="mb-3 flex items-center justify-between gap-3">
          <span className="font-bold">{range}</span>
          <span className="flex items-center gap-1">
            <button type="button" onClick={() => setAsTable(!asTable)} className="text-brand-700 mr-2 text-sm font-bold">
              {asTable ? 'Show chart' : 'Show table'}
            </button>
            <button
              type="button"
              aria-label="Earlier days"
              disabled={!data.hasEarlier}
              onClick={() => setPage(page + 1)}
              className="hover:bg-brand-50 rounded-lg p-1.5 disabled:opacity-30"
            >
              <ChevronLeft className="size-5" aria-hidden />
            </button>
            <button
              type="button"
              aria-label="Later days"
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
              className="hover:bg-brand-50 rounded-lg p-1.5 disabled:opacity-30"
            >
              <ChevronRight className="size-5" aria-hidden />
            </button>
          </span>
        </div>

        {asTable ? (
          <div className="scroll-thin max-h-72 overflow-auto">
            <table className="w-full text-sm">
              <thead className="text-muted sticky top-0 bg-white text-left">
                <tr>
                  <th className="py-1 pr-3 font-semibold">Day</th>
                  {chart.series.map((item) => (
                    <th key={item.key} className="py-1 pr-3 text-right font-semibold whitespace-nowrap">
                      {item.key}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...data.days].reverse().map((day) => (
                  <tr key={day} className="border-line border-t">
                    <td className="py-1.5 pr-3 whitespace-nowrap">{shortDay(day)}</td>
                    {chart.series.map((item) => (
                      <td key={item.key} className="py-1.5 pr-3 text-right tabular-nums">
                        {usd(chart.cost(day, item.key))}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <StackedBars days={data.days} series={chart.series} valueOf={chart.cost} />
        )}

        {chart.series.length > 0 && (
          <ul className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 lg:grid-cols-4">
            {chart.series.map((item) => (
              <li key={item.key} className="flex min-w-0 gap-2.5">
                <span className="w-1 shrink-0 rounded-full" style={{ background: item.color }} aria-hidden />
                <span className="min-w-0">
                  <span className="text-muted block truncate text-sm">{item.key}</span>
                  <span className="block text-xl font-extrabold tabular-nums">
                    {percentText(chart.totalCost ? (item.cost / chart.totalCost) * 100 : 0)}
                  </span>
                  <span className="text-muted block text-xs tabular-nums">{usd(item.cost)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="mt-4">
        <CardTitle hint={`${range}. Each is one spoken answer from the voice model.`}>Responses</CardTitle>
        <div className="-mt-1 mb-2 text-3xl font-extrabold tracking-tight tabular-nums">{chart.totalResponses.toLocaleString('en-US')}</div>
        <Lines days={data.days} series={chart.lineSeries} valueOf={chart.lineValue} />
        {chart.lineSeries.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {chart.lineSeries.map((item) => (
              <li key={item.key} className="text-muted flex items-center gap-1.5">
                <span className="size-2.5 rounded-full" style={{ background: item.color }} aria-hidden />
                {item.key}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="mt-4">
        <CardTitle hint="Open a period to see each workstation.">Spending history</CardTitle>
        <div className="grid gap-5 md:grid-cols-2">
          <PeriodTable title="Monthly" rows={data.months} showShare />
          <PeriodTable title="Weekly" rows={data.weeks} showShare={false} />
        </div>
      </Card>
    </>
  );
}
