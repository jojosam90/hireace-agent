'use client';

import { useEffect, useRef, useState } from 'react';
import { Track } from 'livekit-client';
import { VideoTrack, useSessionContext, useTracks } from '@livekit/components-react';
import { MonitorIcon, XIcon } from '@phosphor-icons/react/dist/ssr';
import { Button } from '@/components/ui/button';
import { useUiLanguage } from '@/lib/i18n';

// Must match the agent's src/screen_stream.py TRACK_NAME and the RPC in src/agent.py
const SCREEN_TRACK_NAME = 'pc-screen';
const SCREEN_RPC_METHOD = 'wang.screen_stream';

/**
 * Live view of the PC the agent is controlling, for touch devices (phones,
 * tablets) only: on the PC itself you watch the real screen. The agent streams it as a video track over
 * the call's LiveKit connection, and only while this view is open.
 */
export function PcScreenView() {
  const { t } = useUiLanguage();
  const { room, isConnected } = useSessionContext();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const screenTrack = useTracks([Track.Source.ScreenShare]).find(
    (track) => track.publication.trackName === SCREEN_TRACK_NAME
  );

  const setStream = async (on: boolean) => {
    const agent = room && [...room.remoteParticipants.values()].find((p) => p.isAgent);
    if (!agent) throw new Error(t('pcScreenUnavailable'));
    await room.localParticipant.performRpc({
      destinationIdentity: agent.identity,
      method: SCREEN_RPC_METHOD,
      payload: JSON.stringify({ on }),
    });
  };

  const show = async () => {
    setError(null);
    setOpen(true);
    try {
      await setStream(true);
    } catch {
      setError(t('pcScreenUnavailable'));
    }
  };

  const close = () => {
    setOpen(false);
    setStream(false).catch(() => {
      // the call may already be over
    });
  };

  // A call that ends (End call, "goodbye", dropped connection) closes the view
  const wasConnected = useRef(false);
  useEffect(() => {
    if (wasConnected.current && !isConnected) setOpen(false);
    wasConnected.current = isConnected;
  }, [isConnected]);

  if (!isConnected) return null;

  if (!open) {
    return (
      <Button
        variant="outline"
        size="sm"
        className="fixed top-4 left-14 z-50 md:left-40 pointer-fine:hidden"
        onClick={show}
      >
        <MonitorIcon />
        {t('pcScreenButton')}
      </Button>
    );
  }

  return (
    <section
      aria-label={t('pcScreenTitle')}
      className="bg-background fixed inset-0 z-40 flex flex-col pointer-fine:hidden"
    >
      <div className="bg-muted flex h-10 shrink-0 items-center gap-2 border-b px-3 select-none">
        <MonitorIcon className="text-muted-foreground" />
        <span className="flex-1 truncate text-sm font-medium">{t('pcScreenTitle')}</span>
        <Button variant="ghost" size="icon-xs" title={t('closePcScreen')} onClick={close}>
          <XIcon />
        </Button>
      </div>
      <div className="flex flex-1 items-center justify-center overflow-hidden bg-black">
        {screenTrack ? (
          <VideoTrack trackRef={screenTrack} className="h-full w-full object-contain" />
        ) : (
          <p className="text-muted-foreground px-6 text-center text-sm">
            {error ?? t('pcScreenConnecting')}
          </p>
        )}
      </div>
    </section>
  );
}
