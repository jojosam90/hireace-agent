import { useEffect, useState } from 'react';
import { useAgent, useSessionContext } from '@livekit/components-react';

export type OnlineStatus = 'online' | 'connecting' | 'offline' | 'unknown';

const CHECK_EVERY_MS = 10_000;

/**
 * Whether HireAce is there for the user. In a call: whether the agent has joined
 * and is working. Between calls: whether HireAce is running on the PC (checked
 * every 10 s, a tiny request; "unknown" on the phone site, which cannot see the PC
 * until a call starts).
 */
export function useOnlineStatus(): OnlineStatus {
  const { isConnected } = useSessionContext();
  const agent = useAgent();
  const [pc, setPc] = useState<OnlineStatus>('unknown');

  useEffect(() => {
    if (isConnected) return; // the call says it
    let stopped = false;
    const check = async () => {
      try {
        const res = await fetch('/api/status', { cache: 'no-store' });
        const { state } = await res.json();
        if (!stopped) setPc(state);
      } catch {
        if (!stopped) setPc('offline');
      }
    };
    check();
    const timer = setInterval(check, CHECK_EVERY_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [isConnected]);

  if (!isConnected) return pc;
  if (['listening', 'thinking', 'speaking'].includes(agent.state)) return 'online';
  if (agent.state === 'failed' || agent.state === 'disconnected') return 'offline';
  return 'connecting';
}
