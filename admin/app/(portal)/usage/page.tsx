'use client';

import { AlertTriangle, BellRing, Check, LoaderCircle, Mail, Receipt, Save, TrendingUp, Wallet, XCircle } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { RankBars, TokenTable } from '@/components/charts';
import { OpenAIBill, UsageHistory } from '@/components/usage-history';
import { Badge, Button, Card, CardTitle, Empty, Loading, Meter, Page, Problem, Stat } from '@/components/ui';
import { call, usePoll } from '@/lib/client';
import { ago, usd } from '@/lib/format';
import type { AlertsData, AlertView, PortalSettings, UsageData } from '@/lib/types';

const PRICES: [keyof PortalSettings['prices'], string][] = [
  ['inAudio', 'Audio in'],
  ['cachedAudio', 'Audio in, cached'],
  ['outAudio', 'Audio out'],
  ['inText', 'Text in'],
  ['cachedText', 'Text in, cached'],
  ['outText', 'Text out'],
  ['inImage', 'Images in'],
];

function Field({ id, label, hint, error, children }: { id: string; label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="text-sm font-semibold">
        {label}
      </label>
      <div className="mt-1">{children}</div>
      {hint && !error && <p className="text-muted mt-1 text-xs">{hint}</p>}
      {error && <p className="mt-1 text-xs font-bold text-red-700">{error}</p>}
    </div>
  );
}

function alertNote(alert: AlertView, emailReady: boolean) {
  if (alert.email_error) return `Email failed: ${alert.email_error}`;
  if (alert.emailed_at) return 'Emailed';
  return emailReady ? '' : 'Shown here only';
}

function SpendingAlerts({ refresh }: { refresh: number }) {
  const { data, error, reload } = usePoll<AlertsData>(`/api/admin/alerts?r=${refresh}`, 30_000);
  const [problem, setProblem] = useState('');
  if (!data) return error ? <Problem>{error}</Problem> : null;

  async function acknowledge(id?: string) {
    setProblem('');
    try {
      await call('/api/admin/alerts', 'PATCH', { id });
      reload();
    } catch (failure) {
      setProblem(failure instanceof Error ? failure.message : 'Could not do that.');
    }
  }

  return (
    <Card className="mt-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <CardTitle hint="They tell you; they do not stop calls. That is the At the limit setting below.">Spending alerts</CardTitle>
        {data.open.length > 1 && (
          <Button icon={Check} onClick={() => acknowledge()}>
            Acknowledge all
          </Button>
        )}
      </div>
      {problem && <Problem>{problem}</Problem>}
      {data.open.length === 0 ? (
        <p className="text-muted flex items-center gap-2 text-sm font-semibold">
          <BellRing className="text-brand-600 size-4" aria-hidden />
          No open alerts.
        </p>
      ) : (
        <ul className="divide-line scroll-thin max-h-80 divide-y overflow-y-auto">
          {data.open.map((alert) => {
            const Icon = alert.severity === 'critical' ? XCircle : AlertTriangle;
            return (
              <li key={alert.id} className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 py-3 text-sm">
                <span className="flex min-w-0 flex-1 basis-64 gap-2.5">
                  <Icon className={`mt-0.5 size-4 shrink-0 ${alert.severity === 'critical' ? 'text-red-600' : 'text-amber-600'}`} aria-hidden />
                  <span className="min-w-0">
                    <strong className="block">{alert.title}</strong>
                    <span className="text-muted block">{alert.detail}</span>
                    <span className="text-muted block text-xs">
                      {ago(alert.created_at)}
                      {alertNote(alert, data.emailReady) && ` · ${alertNote(alert, data.emailReady)}`}
                    </span>
                  </span>
                </span>
                <Button onClick={() => acknowledge(alert.id)}>Acknowledge</Button>
              </li>
            );
          })}
        </ul>
      )}
      {data.past.length > 0 && (
        <details className="mt-3">
          <summary className="text-brand-700 cursor-pointer text-sm font-bold">Earlier alerts</summary>
          <ul className="divide-line scroll-thin mt-2 max-h-60 divide-y overflow-y-auto text-sm">
            {data.past.map((alert) => (
              <li key={alert.id} className="py-2">
                <strong>{alert.title}</strong>
                <span className="text-muted"> · {alert.detail} · {ago(alert.created_at)} · {alert.acknowledged_by}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}

const inputClass =
  'bg-field border-line focus:border-brand-500 h-10 w-full rounded-xl border px-3 text-sm outline-none focus:bg-white';

/** Limits are typed as text: empty means no limit. */
function Limits({ onSaved }: { onSaved: () => void }) {
  const [form, setForm] = useState<Record<string, string> | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [problem, setProblem] = useState('');
  const [emailNote, setEmailNote] = useState('');

  useEffect(() => {
    call<PortalSettings>('/api/admin/settings')
      .then((settings) =>
        setForm({
          monthlyBudgetUsd: settings.monthlyBudgetUsd?.toString() ?? '',
          deviceMonthlyUsd: settings.deviceMonthlyUsd?.toString() ?? '',
          warnPercent: String(settings.warnPercent),
          alertPercents: settings.alertPercents.join(', '),
          dailyAlertUsd: settings.dailyAlertUsd?.toString() ?? '',
          paceAlert: settings.paceAlert ? 'yes' : 'no',
          alertEmails: settings.alertEmails.join(', '),
          atLimit: settings.atLimit,
          heartbeatSeconds: String(settings.heartbeatSeconds),
          offlineAfterSeconds: String(settings.offlineAfterSeconds),
          ...Object.fromEntries(PRICES.map(([key]) => [`prices.${key}`, String(settings.prices[key])])),
        }),
      )
      .catch((error) => setProblem(error.message));
  }, []);

  if (problem) return <Problem>{problem}</Problem>;
  if (!form) return <Loading />;

  const set = (key: string) => (event: { target: { value: string } }) => {
    setSaved(false);
    setForm({ ...form, [key]: event.target.value });
  };
  const optional = (value: string) => (value.trim() ? Number(value) : null);
  const list = (value: string) => value.split(',').map((part) => part.trim()).filter(Boolean);

  async function testEmail() {
    setEmailNote('Sending…');
    try {
      await call('/api/admin/alerts/test', 'POST');
      setEmailNote('Sent. Check the inbox.');
    } catch (error) {
      setEmailNote(error instanceof Error ? error.message : 'Could not send.');
    }
  }

  async function save() {
    setBusy(true);
    setSaved(false);
    setProblem('');
    try {
      const result = await call<{ saved: boolean; errors: Record<string, string> }>('/api/admin/settings', 'PUT', {
        monthlyBudgetUsd: optional(form!.monthlyBudgetUsd),
        deviceMonthlyUsd: optional(form!.deviceMonthlyUsd),
        warnPercent: Number(form!.warnPercent),
        alertPercents: list(form!.alertPercents).map(Number),
        dailyAlertUsd: optional(form!.dailyAlertUsd),
        paceAlert: form!.paceAlert === 'yes',
        alertEmails: list(form!.alertEmails),
        atLimit: form!.atLimit,
        heartbeatSeconds: Number(form!.heartbeatSeconds),
        offlineAfterSeconds: Number(form!.offlineAfterSeconds),
        prices: Object.fromEntries(PRICES.map(([key]) => [key, Number(form![`prices.${key}`])])),
      });
      setErrors(result.errors);
      setSaved(result.saved);
      if (result.saved) onSaved();
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'Could not save.');
    }
    setBusy(false);
  }

  return (
    <Card className="mt-4">
      <CardTitle hint="Spend counts from the 1st of each month, UTC, like OpenAI's bill.">Limits and alert settings</CardTitle>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field id="budget" label="Monthly budget, all PCs (US$)" hint="Empty: no limit" error={errors.monthlyBudgetUsd}>
          <input id="budget" inputMode="decimal" value={form.monthlyBudgetUsd} onChange={set('monthlyBudgetUsd')} className={inputClass} />
        </Field>
        <Field id="each" label="Monthly limit, each PC (US$)" hint="Empty: no limit. A PC can have its own." error={errors.deviceMonthlyUsd}>
          <input id="each" inputMode="decimal" value={form.deviceMonthlyUsd} onChange={set('deviceMonthlyUsd')} className={inputClass} />
        </Field>
        <Field id="warn" label="Warn at (% of a limit)" error={errors.warnPercent}>
          <input id="warn" inputMode="numeric" value={form.warnPercent} onChange={set('warnPercent')} className={inputClass} />
        </Field>
      </div>

      <fieldset className="mt-4">
        <legend className="text-sm font-semibold">At the limit</legend>
        <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
          {[
            ['warn', 'Only warn me', 'Calls keep working and spending continues.'],
            ['block', 'Refuse new calls', 'A call that is open finishes. HireAce says the limit was reached.'],
          ].map(([value, title, text]) => (
            <label
              key={value}
              className={`flex cursor-pointer gap-3 rounded-xl border p-3 ${
                form.atLimit === value ? 'border-brand-500 bg-brand-50' : 'border-line'
              }`}
            >
              <input
                type="radio"
                name="atLimit"
                value={value}
                checked={form.atLimit === value}
                onChange={set('atLimit')}
                className="accent-brand-600 mt-1"
              />
              <span className="text-sm">
                <span className="block font-bold">{title}</span>
                <span className="text-muted">{text}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="border-line mt-5 border-t pt-4">
        <legend className="pr-2 text-sm font-semibold">Spending alerts</legend>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field id="steps" label="Alert at (% of a limit)" hint="Separated by commas. Reaching 100% always alerts." error={errors.alertPercents}>
            <input id="steps" value={form.alertPercents} onChange={set('alertPercents')} className={inputClass} />
          </Field>
          <Field id="daily" label="Alert if one day passes (US$)" hint="All PCs together. Empty: no alert." error={errors.dailyAlertUsd}>
            <input id="daily" inputMode="decimal" value={form.dailyAlertUsd} onChange={set('dailyAlertUsd')} className={inputClass} />
          </Field>
          <Field id="emails" label="Email alerts to" hint="Separated by commas. Empty: shown here only." error={errors.alertEmails}>
            <input id="emails" inputMode="email" value={form.alertEmails} onChange={set('alertEmails')} className={inputClass} />
          </Field>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold">
            <input
              type="checkbox"
              checked={form.paceAlert === 'yes'}
              onChange={(event) => set('paceAlert')({ target: { value: event.target.checked ? 'yes' : 'no' } })}
              className="accent-brand-600 size-4"
            />
            Alert when the month is on pace to go over the budget
          </label>
          <span className="flex flex-wrap items-center gap-2">
            {emailNote && (
              <span role="status" className="text-muted text-sm font-semibold">
                {emailNote}
              </span>
            )}
            <Button icon={Mail} onClick={testEmail}>
              Send a test email
            </Button>
          </span>
        </div>
      </fieldset>

      <details className="mt-4">
        <summary className="text-brand-700 cursor-pointer text-sm font-bold">Check-in timing and OpenAI prices</summary>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <Field id="beat" label="Check in every (seconds)" hint="30 to 900. More often costs more server requests." error={errors.heartbeatSeconds}>
            <input id="beat" inputMode="numeric" value={form.heartbeatSeconds} onChange={set('heartbeatSeconds')} className={inputClass} />
          </Field>
          <Field id="off" label="Offline after (seconds)" hint="Allow at least two missed check-ins." error={errors.offlineAfterSeconds}>
            <input id="off" inputMode="numeric" value={form.offlineAfterSeconds} onChange={set('offlineAfterSeconds')} className={inputClass} />
          </Field>
        </div>
        <p className="text-muted mt-4 text-sm">
          US$ per 1M tokens, for the estimates. New usage uses these prices; earlier usage keeps the price it was counted at.
        </p>
        <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {PRICES.map(([key, label]) => (
            <Field key={key} id={key} label={label} error={errors[`prices.${key}`]}>
              <input id={key} inputMode="decimal" value={form[`prices.${key}`]} onChange={set(`prices.${key}`)} className={inputClass} />
            </Field>
          ))}
        </div>
      </details>

      <div className="mt-5 flex items-center gap-3">
        <Button kind="primary" icon={busy ? LoaderCircle : Save} disabled={busy} onClick={save}>
          Save limits
        </Button>
        {saved && (
          <span role="status" className="text-sm font-bold text-emerald-800">
            Saved. Workstations follow at their next check-in.
          </span>
        )}
        {Object.keys(errors).length > 0 && !saved && (
          <span role="alert" className="text-sm font-bold text-red-700">
            Check the fields marked in red.
          </span>
        )}
      </div>
    </Card>
  );
}

export default function UsagePage() {
  const { data, error, reload } = usePoll<UsageData>('/api/admin/usage', 30_000);
  const [saves, setSaves] = useState(0);
  if (!data) return error ? <Problem>{error}</Problem> : <Loading />;
  const percent = data.budgetUsd ? Math.round((data.monthCostUsd / data.budgetUsd) * 100) : null;

  return (
    <Page
      title="OpenAI usage"
      intro="The real bill from OpenAI, and an estimate per workstation from the tokens each PC reports since it was installed."
    >
      {error && <Problem>Could not refresh. Showing the last known figures.</Problem>}
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat
          label="Estimated this month"
          value={usd(data.monthCostUsd)}
          icon={Wallet}
          note={data.budgetUsd !== null ? `${percent}% of ${usd(data.budgetUsd)}` : 'No budget set'}
        >
          {data.budgetUsd !== null && <Meter value={data.monthCostUsd} limit={data.budgetUsd} warnPercent={data.warnPercent} />}
        </Stat>
        <Stat label="On pace for" value={usd(data.onPaceUsd)} note="If the month carries on like this" icon={TrendingUp} />
        {data.billed ? (
          <Stat
            label="Billed by OpenAI"
            value={usd(data.billed.usd)}
            note="This month, whole organization"
            icon={Receipt}
          />
        ) : (
          <Stat
            label="Billed by OpenAI"
            value="Not connected"
            note={data.adminKeySet ? 'OpenAI did not answer. Check the Admin key.' : 'Needs an OpenAI Admin key on the server.'}
            icon={Receipt}
          />
        )}
      </div>

      {data.billed && <OpenAIBill bill={data.billed} />}

      <SpendingAlerts refresh={saves} />

      <Limits
        onSaved={() => {
          reload();
          setSaves(saves + 1);
        }}
      />

      <UsageHistory />

      <div className="mt-4 grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <CardTitle hint="This month, against each limit">By workstation</CardTitle>
          {data.devices.length === 0 ? (
            <Empty icon={Wallet} title="No usage yet" />
          ) : (
            <div className="scroll-thin max-h-80 overflow-y-auto pr-1">
              <RankBars rows={data.devices} />
            </div>
          )}
        </Card>
        <Card className="lg:col-span-3">
        <CardTitle hint="This month, all workstations">Tokens</CardTitle>
        <TokenTable tokens={data.tokens} />
        {data.models.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {data.models.map((row) => (
              <Badge key={row.model} tone="brand">
                {row.model}: {usd(row.cost)}
              </Badge>
            ))}
          </div>
        )}
        </Card>
      </div>
    </Page>
  );
}
