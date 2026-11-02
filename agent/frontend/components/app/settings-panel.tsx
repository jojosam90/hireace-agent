'use client';

import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { GearSixIcon, XIcon } from '@phosphor-icons/react/dist/ssr';
import { Button } from '@/components/ui/button';
import { type StringKey, useUiLanguage } from '@/lib/i18n';

// Must match FIELDS in the agent's src/settings.py
type Field =
  | 'voice'
  | 'openai_api_key'
  | 'email_signature'
  | 'quote_signature'
  | 'quote_template'
  | 'quote_dir'
  | 'quote_pdf_dir'
  | 'price_list'
  | 'search_dirs';

interface SettingsData {
  values: Record<Field, string>;
  voices: string[];
}

type GmailState = 'ready' | 'signed_out' | 'not_open' | 'closed' | 'error';

interface GmailStatus {
  state: GmailState;
  email: string;
  reason?: string;
}

const BADGE: Record<GmailState, { label: StringKey; className: string }> = {
  ready: {
    label: 'gmailReady',
    className: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  },
  signed_out: {
    label: 'gmailSignedOut',
    className: 'bg-amber-500/15 text-amber-700 dark:text-amber-400',
  },
  not_open: { label: 'gmailNotOpen', className: 'bg-muted text-muted-foreground' },
  closed: { label: 'gmailClosed', className: 'bg-muted text-muted-foreground' },
  error: { label: 'gmailError', className: 'bg-amber-500/15 text-amber-700 dark:text-amber-400' },
};

const TEXT_FIELDS: { section: StringKey; fields: { field: Field; label: StringKey }[] }[] = [
  {
    section: 'sectionSignatures',
    fields: [
      { field: 'email_signature', label: 'emailSignatureLabel' },
      { field: 'quote_signature', label: 'quoteSignatureLabel' },
    ],
  },
  {
    section: 'sectionQuotations',
    fields: [
      { field: 'quote_template', label: 'quoteTemplateLabel' },
      { field: 'quote_dir', label: 'quoteDirLabel' },
      { field: 'quote_pdf_dir', label: 'quotePdfDirLabel' },
      { field: 'price_list', label: 'priceListLabel' },
    ],
  },
  { section: 'sectionFiles', fields: [{ field: 'search_dirs', label: 'searchDirsLabel' }] },
];

const INPUT = 'bg-background w-full rounded-md border px-3 py-2 text-sm';

/** The gear icon (top right) and the Settings screen it opens, over the call. */
export function SettingsPanel() {
  const { t } = useUiLanguage();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <>
      <Button
        variant="outline"
        size="icon"
        className="size-8 rounded-full"
        title={t('settings')}
        aria-label={t('settings')}
        onClick={() => setOpen(true)}
      >
        <GearSixIcon />
      </Button>
      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={t('settings')}
          className="bg-background fixed inset-0 z-[60] overflow-y-auto"
        >
          <div className="mx-auto flex max-w-xl flex-col gap-6 px-4 py-6">
            <div className="flex items-center justify-between">
              <h1 className="text-lg font-semibold">{t('settings')}</h1>
              <Button
                variant="ghost"
                size="icon"
                aria-label={t('settingsClose')}
                autoFocus
                onClick={() => setOpen(false)}
              >
                <XIcon />
              </Button>
            </div>
            <SettingsForm />
          </div>
        </div>
      )}
    </>
  );
}

function SettingsForm() {
  const { t } = useUiLanguage();
  const [data, setData] = useState<SettingsData | null>(null);
  const [problem, setProblem] = useState<StringKey | null>(null);
  const [edits, setEdits] = useState<Partial<Record<Field, string>>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/settings', { cache: 'no-store' });
      if (res.status === 403) return setProblem('settingsPcOnly');
      if (!res.ok) return setProblem('settingsUnavailable');
      setData(await res.json());
      setEdits({});
    } catch {
      setProblem('settingsUnavailable');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (problem) return <p className="text-muted-foreground text-sm">{t(problem)}</p>;
  if (!data) return null;

  const value = (field: Field) => edits[field] ?? data.values[field] ?? '';
  const edit = (field: Field, next: string) => setEdits((e) => ({ ...e, [field]: next }));

  const save = async () => {
    // Only what changed; an empty key keeps the saved one
    const changes = Object.fromEntries(
      Object.entries(edits).filter(
        ([field, v]) => v !== data.values[field as Field] && !(field === 'openai_api_key' && !v)
      )
    );
    setSaving(true);
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(changes),
      });
      const body = await res.json();
      setErrors(body.errors ?? {});
      if (body.saved) {
        toast.success(t('settingsSaved'));
        await load();
      }
    } catch {
      toast.error(t('settingsUnavailable'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      className="flex flex-col gap-6"
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      <Section title={t('sectionEmail')}>
        <GmailStandby />
      </Section>

      <Section title={t('sectionVoice')}>
        <Label text={t('voiceLabel')} error={errors.voice}>
          <select
            className={INPUT}
            value={value('voice')}
            onChange={(e) => edit('voice', e.target.value)}
          >
            {data.voices.map((voice) => (
              <option key={voice} value={voice}>
                {voice}
              </option>
            ))}
          </select>
        </Label>
      </Section>

      {TEXT_FIELDS.map(({ section, fields }) => (
        <Section key={section} title={t(section)}>
          {fields.map(({ field, label }) => (
            <Label key={field} text={t(label)} error={errors[field]}>
              <input
                className={INPUT}
                value={value(field)}
                placeholder={t('settingsDefault')}
                spellCheck={false}
                onChange={(e) => edit(field, e.target.value)}
              />
            </Label>
          ))}
        </Section>
      ))}

      <Section title={t('sectionOpenai')}>
        <Label
          text={t('openaiKeyLabel')}
          error={errors.openai_api_key}
          help={
            data.values.openai_api_key
              ? t('openaiKeySaved', { hint: data.values.openai_api_key })
              : undefined
          }
        >
          <input
            className={INPUT}
            type="password"
            autoComplete="off"
            value={edits.openai_api_key ?? ''}
            placeholder="sk-…"
            onChange={(e) => edit('openai_api_key', e.target.value)}
          />
        </Label>
      </Section>

      <Button type="submit" disabled={saving} className="self-start">
        {saving ? t('settingsSaving') : t('settingsSave')}
      </Button>
    </form>
  );
}

/** Sender (From): Gmail signed in in HireAce's browser, on standby, and a test email. */
function GmailStandby() {
  const { t } = useUiLanguage();
  const [status, setStatus] = useState<GmailStatus | null>(null);
  const [opening, setOpening] = useState(false);
  const [testTo, setTestTo] = useState('');
  const [testing, setTesting] = useState(false);

  const check = useCallback(async () => {
    try {
      const res = await fetch('/api/gmail', { cache: 'no-store' });
      setStatus(res.ok ? await res.json() : { state: 'error', email: '' });
    } catch {
      setStatus({ state: 'error', email: '' });
    }
  }, []);

  // Checked every few seconds while Settings is open, so it turns Ready as soon
  // as the user has signed in
  useEffect(() => {
    check();
    const timer = setInterval(check, 3000);
    return () => clearInterval(timer);
  }, [check]);

  const openGmail = async () => {
    setOpening(true);
    try {
      const res = await fetch('/api/gmail/open', { method: 'POST' });
      if (res.ok) setStatus(await res.json());
      else toast.error(t('settingsUnavailable'));
    } finally {
      setOpening(false);
    }
  };

  const sendTest = async () => {
    setTesting(true);
    try {
      const res = await fetch('/api/gmail/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to: testTo }),
      });
      const body = await res.json();
      if (body.sent) toast.success(t('testEmailSent', { to: testTo }));
      else toast.error(body.reason ?? t('gmailError'));
    } finally {
      setTesting(false);
    }
  };

  if (!status) return null;
  const badge = BADGE[status.state] ?? BADGE.error;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{t('senderLabel')}</span>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}>
          {t(badge.label)}
        </span>
        {status.email && <span className="text-sm">{status.email}</span>}
      </div>
      <p className="text-muted-foreground text-xs">{t('senderHelp')}</p>
      {status.reason && <p className="text-destructive text-xs">{status.reason}</p>}

      {status.state !== 'ready' && (
        <div className="flex flex-col gap-1">
          <Button
            type="button"
            size="sm"
            className="self-start"
            onClick={openGmail}
            disabled={opening}
          >
            {t('gmailOpen')}
          </Button>
          <span className="text-muted-foreground text-xs">{t('gmailOpenHelp')}</span>
        </div>
      )}

      {status.state === 'ready' && (
        <div className="flex flex-col gap-1">
          <label htmlFor="test-to" className="text-muted-foreground text-xs">
            {t('testEmailLabel')}
          </label>
          <div className="flex gap-2">
            <input
              id="test-to"
              type="email"
              className={INPUT}
              value={testTo}
              placeholder="name@example.com"
              onChange={(e) => setTestTo(e.target.value)}
            />
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-auto"
              disabled={testing || !testTo}
              onClick={sendTest}
            >
              {t('testEmailButton')}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Label({
  text,
  error,
  help,
  children,
}: {
  text: string;
  error?: string;
  help?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span>{text}</span>
      {children}
      {help && <span className="text-muted-foreground text-xs">{help}</span>}
      {error && <span className="text-destructive text-xs">{error}</span>}
    </label>
  );
}
