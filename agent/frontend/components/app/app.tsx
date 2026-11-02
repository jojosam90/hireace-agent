'use client';

import { useMemo } from 'react';
import { TokenSource } from 'livekit-client';
import { useSession } from '@livekit/components-react';
import { WarningIcon } from '@phosphor-icons/react/dist/ssr';
import type { AppConfig } from '@/app-config';
import { AgentSessionProvider } from '@/components/agents-ui/agent-session-provider';
import { StartAudioButton } from '@/components/agents-ui/start-audio-button';
import { ApprovalPanel } from '@/components/app/approval-panel';
import { CallMirror } from '@/components/app/call-mirror';
import { HireAceLogo } from '@/components/app/hireace-logo';
import { LanguageSwitch } from '@/components/app/language-switch';
import { Notifications } from '@/components/app/notifications';
import { PcScreenView } from '@/components/app/pc-screen-view';
import { SettingsPanel } from '@/components/app/settings-panel';
import { ViewController } from '@/components/app/view-controller';
import { ViewModeToggle } from '@/components/app/view-mode-toggle';
import { Toaster } from '@/components/ui/sonner';
import { useAgentErrors } from '@/hooks/useAgentErrors';
import { useDebugMode } from '@/hooks/useDebug';
import { useMicWatchdog } from '@/hooks/useMicWatchdog';
import { useUiLanguage } from '@/lib/i18n';
import { getSandboxTokenSource } from '@/lib/utils';

const IN_DEVELOPMENT = process.env.NODE_ENV !== 'production';

function AppSetup() {
  useDebugMode({ enabled: IN_DEVELOPMENT });
  useAgentErrors();
  useMicWatchdog();

  return null;
}

interface AppProps {
  appConfig: AppConfig;
}

export function App({ appConfig }: AppProps) {
  const { t } = useUiLanguage();
  const tokenSource = useMemo(() => {
    return typeof process.env.NEXT_PUBLIC_CONN_DETAILS_ENDPOINT === 'string'
      ? getSandboxTokenSource(appConfig)
      : TokenSource.endpoint('/api/token');
  }, [appConfig]);

  const session = useSession(
    tokenSource,
    appConfig.agentName ? { agentName: appConfig.agentName } : undefined
  );

  return (
    <AgentSessionProvider session={session}>
      <AppSetup />
      <main className="@container relative z-10 grid h-svh grid-cols-1 place-content-center">
        <ViewController appConfig={appConfig} />
      </main>
      <CallMirror />
      <HireAceLogo />
      <PcScreenView />
      <Notifications />
      <ViewModeToggle />
      <StartAudioButton label={t('startAudio')} />
      <ApprovalPanel />
      <div className="fixed top-4 right-4 z-50 flex items-center gap-2">
        <SettingsPanel />
        <LanguageSwitch />
      </div>
      <Toaster
        icons={{
          warning: <WarningIcon weight="bold" />,
        }}
        position="top-center"
        className="toaster group"
        style={
          {
            '--normal-bg': 'var(--popover)',
            '--normal-text': 'var(--popover-foreground)',
            '--normal-border': 'var(--border)',
          } as React.CSSProperties
        }
      />
    </AgentSessionProvider>
  );
}
