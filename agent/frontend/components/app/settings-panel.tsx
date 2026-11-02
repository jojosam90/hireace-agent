'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { GearSixIcon, XIcon } from '@phosphor-icons/react/dist/ssr';
import { Button } from '@/components/ui/button';
import { type StringKey, useUiLanguage } from '@/lib/i18n';

interface SettingsData {
  values: { voice: string };
  voices: string[];
}

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

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch('/api/settings', { cache: 'no-store' });
        if (res.status === 403) return setProblem('settingsPcOnly');
        if (!res.ok) return setProblem('settingsUnavailable');
        setData(await res.json());
      } catch {
        setProblem('settingsUnavailable');
      }
    };
    load();
  }, []);

  if (problem) return <p className="text-muted-foreground text-sm">{t(problem)}</p>;
  if (!data) return null;

  // Saved as soon as it is chosen
  const choose = async (voice: string) => {
    const previous = data.values.voice;
    setData({ ...data, values: { voice } });
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice }),
      });
      if (!(await res.json()).saved) throw new Error('not saved');
      toast.success(t('settingsSaved'));
    } catch {
      setData({ ...data, values: { voice: previous } });
      toast.error(t('settingsUnavailable'));
    }
  };

  return (
    <label className="flex flex-col gap-1 text-sm">
      <span>{t('voiceLabel')}</span>
      <select className={INPUT} value={data.values.voice} onChange={(e) => choose(e.target.value)}>
        {data.voices.map((voice) => (
          <option key={voice} value={voice}>
            {voice}
          </option>
        ))}
      </select>
    </label>
  );
}
