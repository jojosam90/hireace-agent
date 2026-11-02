'use client';

import { useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { CheckIcon, CopyIcon, DeviceMobileIcon } from '@phosphor-icons/react/dist/ssr';
import { Button } from '@/components/ui/button';
import { useUiLanguage } from '@/lib/i18n';
import { phoneLink } from '@/lib/phone-link';

/**
 * This PC's link to the shared web app, as a QR code to scan with a phone. Only on
 * the PC itself (mouse): a phone that is already on the site does not need it.
 */
export function PhoneLink({ siteUrl, agentName }: { siteUrl: string; agentName: string }) {
  const { t } = useUiLanguage();
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const link = phoneLink(siteUrl, agentName);

  const copy = async () => {
    await navigator.clipboard.writeText(link);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="mt-6 flex flex-col items-center gap-3 pointer-coarse:hidden">
      <Button variant="ghost" size="sm" onClick={() => setOpen((v) => !v)}>
        <DeviceMobileIcon />
        {t('useFromPhone')}
      </Button>
      {open && (
        <div className="flex w-64 flex-col items-center gap-3 rounded-xl border p-4">
          <div className="rounded-md bg-white p-2">
            <QRCodeSVG value={link} size={160} />
          </div>
          <p className="text-muted-foreground text-xs leading-5">{t('phoneLinkHelp')}</p>
          <p className="font-mono text-xs break-all select-all">{link}</p>
          <Button variant="outline" size="sm" onClick={copy}>
            {copied ? <CheckIcon /> : <CopyIcon />}
            {copied ? t('copied') : t('copyLink')}
          </Button>
        </div>
      )}
    </div>
  );
}
