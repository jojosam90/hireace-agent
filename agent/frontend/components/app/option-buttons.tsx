'use client';

import { useChat } from '@livekit/components-react';
import { Button } from '@/components/ui/button';
import { useUiLanguage } from '@/lib/i18n';

export interface Option {
  key: string;
  label: string;
}

// "A) ", "B. ", "C: " after a space or, in Chinese, right after punctuation or a
// character ("？A）", "要我A）")
const MARKER = /(?<=^|[\s，。？！：；、一-鿿])([A-C])[).:）]\s*/g;

/**
 * Options the agent offers as "A) ..., B) ..., C) ..." in one message (A first, at
 * least two). Empty when the message offers none.
 */
export function parseOptions(text: string): Option[] {
  const markers = [...text.matchAll(MARKER)];
  if (markers.length < 2 || markers[0][1] !== 'A') return [];
  const options = markers.map((match, i) => {
    const start = (match.index ?? 0) + match[0].length;
    const end = i + 1 < markers.length ? markers[i + 1].index : text.length;
    const label = text
      .slice(start, end)
      // An option ends with its sentence: "...or C) do both. Which would you like?"
      .split(/(?<=[.?!])\s|(?<=[。？！])/)[0]
      .trim()
      .replace(/[,;，、]?\s*(or|或者|或|还是)?\s*$/i, '') // joiners before the next option
      .replace(/[.?!。？！]+$/, '')
      .trim();
    return { key: match[1], label };
  });
  // Letters must run A, B, C in order
  return options.every((o, i) => o.key === 'ABC'[i] && o.label) ? options : [];
}

/** Tap to choose: sends the choice as the user's chat message. */
export function OptionButtons({ options }: { options: Option[] }) {
  const { t } = useUiLanguage();
  const { send, isSending } = useChat();
  if (options.length === 0) return null;
  return (
    <div role="group" aria-label={t('optionsLabel')} className="mt-2 flex flex-col gap-1.5">
      {options.map((option) => (
        <Button
          key={option.key}
          variant="outline"
          size="sm"
          disabled={isSending}
          className="h-auto justify-start py-1.5 text-left whitespace-normal"
          onClick={() => send(`${option.key}) ${option.label}`)}
        >
          <span className="font-semibold">{option.key}</span>
          {option.label}
        </Button>
      ))}
    </div>
  );
}
