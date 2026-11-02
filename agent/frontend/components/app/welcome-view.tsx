'use client';

import { GmailHealthBar } from '@/components/app/gmail-health-bar';
import { PhoneLink } from '@/components/app/phone-link';
import { Button } from '@/components/ui/button';
import { useUiLanguage } from '@/lib/i18n';

interface WelcomeViewProps {
  onStartCall: () => void;
  // Unset on the shared site until it is opened with a PC's phone link
  agentName?: string;
  phoneSiteUrl?: string;
}

export const WelcomeView = ({
  onStartCall,
  agentName,
  phoneSiteUrl,
  ref,
}: React.ComponentProps<'div'> & WelcomeViewProps) => {
  const { t } = useUiLanguage();
  return (
    <div ref={ref}>
      <section className="flex flex-col items-center justify-center px-4 text-center">
        <p className="text-foreground max-w-prose pt-1 leading-6 font-medium">{t('welcomeText')}</p>

        {agentName ? (
          <Button
            size="lg"
            onClick={onStartCall}
            className="mt-6 w-64 rounded-full font-mono text-xs font-bold tracking-wider uppercase"
          >
            {t('startButton')}
          </Button>
        ) : (
          <p className="text-muted-foreground mt-6 max-w-xs text-sm leading-6">
            {t('needPhoneLink')}
          </p>
        )}

        {agentName && phoneSiteUrl && <PhoneLink siteUrl={phoneSiteUrl} agentName={agentName} />}
        <GmailHealthBar />
      </section>
    </div>
  );
};
