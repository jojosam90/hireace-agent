import { ReactNode, useEffect, useRef } from 'react';
import { toast as sonnerToast } from 'sonner';
import { useAgent, useSessionContext } from '@livekit/components-react';
import { InfoIcon, WarningIcon } from '@phosphor-icons/react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useUiLanguage } from '@/lib/i18n';

// One id: a repeated notice replaces the visible one instead of stacking
const SESSION_TOAST_ID = 'session-ended';

interface ToastProps {
  title: ReactNode;
  description: ReactNode;
  warning: boolean;
  // Until tapped, for notices that need action (e.g. start HireAce on the PC)
  sticky?: boolean;
}

export function toastAlert({ title, description, warning, sticky }: ToastProps) {
  return sonnerToast.custom(
    (id) => (
      <Alert onClick={() => sonnerToast.dismiss(id)} className="bg-accent w-full md:w-[364px]">
        {warning ? <WarningIcon weight="bold" /> : <InfoIcon weight="bold" />}
        <AlertTitle>{title}</AlertTitle>
        {description && <AlertDescription>{description}</AlertDescription>}
      </Alert>
    ),
    { id: SESSION_TOAST_ID, duration: sticky ? Infinity : 6_000 }
  );
}

export function useAgentErrors() {
  const agent = useAgent();
  const { isConnected, end } = useSessionContext();
  const { t } = useUiLanguage();
  const notified = useRef(false);

  useEffect(() => {
    if (!isConnected) {
      notified.current = false; // ready for the next call
      return;
    }
    if (agent.state !== 'failed' || notified.current) return;
    notified.current = true;

    const reasons = agent.failureReasons;
    // The agent leaving is how a call normally ends (e.g. the user said goodbye)
    const agentEndedCall = reasons.some((reason) => /left the room/i.test(reason));
    // Nobody answered: HireAce is not running on that PC (or it is off)
    const pcNotAnswering = reasons.some((reason) => /did not join|timed? ?out/i.test(reason));
    if (!agentEndedCall) {
      console.warn('Session ended:', reasons);
    }

    toastAlert({
      title: agentEndedCall
        ? t('callEnded')
        : pcNotAnswering
          ? t('pcNotAnswering')
          : t('sessionEnded'),
      description: agentEndedCall
        ? t('agentEndedCall')
        : pcNotAnswering
          ? t('pcNotAnsweringHelp')
          : t('connectionProblem'),
      warning: !agentEndedCall,
      sticky: pcNotAnswering,
    });

    end();
  }, [agent.state, agent.failureReasons, isConnected, end, t]);
}
