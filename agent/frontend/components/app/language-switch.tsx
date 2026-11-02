'use client';

import { useState, useTransition } from 'react';
import { useSessionContext } from '@livekit/components-react';
import { type Language, useUiLanguage } from '@/lib/i18n';

const OPTIONS: { value: Language; label: string; title: string }[] = [
  { value: 'en', label: 'EN', title: 'English' },
  { value: 'zh', label: '中文', title: '普通话 Mandarin' },
];

/**
 * Chooses the language of the whole UI and the language HireAce speaks. The token
 * route passes it to the agent when a call starts, so it can only change between calls.
 */
export function LanguageSwitch() {
  const { isConnected } = useSessionContext();
  const { language, setLanguage, t } = useUiLanguage();
  // The pill moves at once; the page changes language right after, without
  // holding up the tap
  const [shown, setShown] = useState(language);
  const [, startTransition] = useTransition();
  const choose = (next: Language) => {
    setShown(next);
    startTransition(() => setLanguage(next));
  };

  return (
    <div
      role="radiogroup"
      aria-label={t('language')}
      title={isConnected ? t('languageLocked') : t('language')}
      className="bg-background flex rounded-full border p-0.5 text-xs font-medium shadow-xs"
    >
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={shown === option.value}
          title={option.title}
          disabled={isConnected}
          onClick={() => choose(option.value)}
          className={`rounded-full px-3 py-1 transition-colors disabled:cursor-not-allowed ${
            shown === option.value
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground disabled:opacity-50'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
