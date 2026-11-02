'use client';

import { useEffect, useRef, useState } from 'react';
import { ConnectionState, Room, RoomEvent } from 'livekit-client';
import { Streamdown } from 'streamdown';
import { useSessionContext, useTranscriptions } from '@livekit/components-react';
import { tidyCjkSpacing } from '@/components/agents-ui/agent-chat-transcript';
import { Bubble, BubbleContent } from '@/components/ui/bubble';
import { Message, MessageContent } from '@/components/ui/message';
import { useUiLanguage } from '@/lib/i18n';

const CHECK_EVERY_MS = 2000;
// The user gone this long: the call is over. The panel leaves by itself, so it never
// keeps a finished call's room open
const NO_USER_MS = 8000;
// The user's identity from app/api/token/route.ts
const USER_IDENTITY = 'voice_assistant_user_';

/**
 * On the PC's panel: when a call runs that this panel did not start (from the phone),
 * joins it by itself and shows the conversation live until it ends. Read-only: it
 * cannot be heard or publish anything. Approve cards show as usual (approval-panel).
 */
export function CallMirror() {
  const { isConnected, room: ownRoom } = useSessionContext();
  const [mirror, setMirror] = useState<Room | null>(null);
  // Calls not to join: this panel's own, and ones already followed to their end
  const skip = useRef(new Set<string>());

  useEffect(() => {
    if (ownRoom?.name) skip.current.add(ownRoom.name);
  }, [ownRoom?.name, isConnected]);

  useEffect(() => {
    // Only the PC can see its own calls (the phone site has no gatekeeper)
    if (isConnected || !['localhost', '127.0.0.1'].includes(window.location.hostname)) return;

    let stopped = false;
    let current: Room | null = null;
    let joining = false;
    let userSeenAt = 0;

    const leave = () => {
      current?.disconnect();
      current = null;
      setMirror(null);
    };

    const check = async () => {
      if (joining) return;
      try {
        const res = await fetch('/api/mirror', { cache: 'no-store' });
        const call: { room: string | null; url?: string; token?: string } = await res.json();
        if (stopped) return;
        if (current && current.name !== call.room) leave();
        if (current) {
          const users = [...current.remoteParticipants.keys()];
          if (users.some((identity) => identity.startsWith(USER_IDENTITY))) {
            userSeenAt = Date.now();
          } else if (Date.now() - userSeenAt > NO_USER_MS) {
            current.disconnect();
          }
        }
        // This panel starting its own call: not one to follow
        const ownBusy = ownRoom && ownRoom.state !== ConnectionState.Disconnected;
        if (
          current ||
          !call.room ||
          !call.url ||
          !call.token ||
          ownBusy ||
          skip.current.has(call.room)
        ) {
          return;
        }

        const name = call.room;
        joining = true;
        const room = new Room();
        room.on(RoomEvent.Disconnected, () => {
          skip.current.add(name);
          if (current === room) {
            current = null;
            setMirror(null);
          }
        });
        await room.connect(call.url, call.token);
        if (stopped) {
          room.disconnect();
          return;
        }
        current = room;
        setMirror(room);
        userSeenAt = Date.now();
      } catch {
        // HireAce or the network not ready: try again on the next tick
      } finally {
        joining = false;
      }
    };

    check();
    const timer = setInterval(check, CHECK_EVERY_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
      leave();
    };
  }, [isConnected, ownRoom]);

  return mirror ? <MirrorView room={mirror} /> : null;
}

function MirrorView({ room }: { room: Room }) {
  const { t } = useUiLanguage();
  const transcriptions = useTranscriptions({ room });
  const end = useRef<HTMLDivElement>(null);

  const lines = transcriptions
    .filter((line) => line.text.trim() !== '')
    .sort((a, b) => a.streamInfo.timestamp - b.streamInfo.timestamp);
  const last = lines.at(-1)?.text;

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' });
  }, [lines.length, last]);

  return (
    <div className="bg-background fixed inset-0 z-40 flex flex-col px-4 pt-16 pb-4">
      <p className="text-muted-foreground flex items-center justify-center gap-2 pb-3 text-xs font-medium">
        <span className="size-2 rounded-full bg-emerald-500" aria-hidden />
        {t('mirrorTitle')}
      </p>
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto" aria-live="polite">
        {lines.length === 0 && (
          <p className="text-muted-foreground m-auto text-sm">{t('mirrorWaiting')}</p>
        )}
        {lines.map((line) => {
          const isUser = line.participantInfo.identity.startsWith(USER_IDENTITY);
          return (
            <Message key={line.streamInfo.id} align={isUser ? 'end' : 'start'}>
              <MessageContent>
                <Bubble align={isUser ? 'end' : 'start'} variant={isUser ? 'secondary' : 'hireace'}>
                  <BubbleContent>
                    <Streamdown>{tidyCjkSpacing(line.text)}</Streamdown>
                  </BubbleContent>
                </Bubble>
              </MessageContent>
            </Message>
          );
        })}
        <div ref={end} />
      </div>
    </div>
  );
}
