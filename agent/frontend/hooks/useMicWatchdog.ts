import { useEffect } from 'react';
import {
  type LocalTrackPublication,
  ParticipantEvent,
  Room,
  Track,
  type TrackPublication,
} from 'livekit-client';
import {
  usePersistentUserChoices,
  useRoomContext,
  useSessionContext,
} from '@livekit/components-react';
import { toastAlert } from '@/hooks/useAgentErrors';
import { useUiLanguage } from '@/lib/i18n';

// Must match CLIENT_LOG_TOPIC in agent.py: these lines go to the agent's log
const CLIENT_LOG_TOPIC = 'hireace.client-log';
const MAX_REOPENS_PER_MINUTE = 3;

// When the user last pressed the mic button: their own mute is left alone
let userToggledAt = 0;
export function noteUserMicToggle() {
  userToggledAt = Date.now();
}

/**
 * Keeps the microphone working during a call. When Windows resets an audio device
 * (e.g. after sleep), the browser ends the mic stream and LiveKit mutes the mic for
 * good: HireAce then hears nothing and seems to hang. This reopens the mic and unmutes
 * it, or says clearly that the mic is lost. Every step goes to the agent's log.
 */
// The laptop's own microphone (Windows names it "Microphone Array")
const BUILT_IN_MIC = /array|built-?in|internal/i;
// Not microphones: Windows' "what you hear" recorder
const NOT_A_MIC = /stereo mix|what u hear/i;

/**
 * The mic to switch to at the start of a call, if not the one in use: the one the
 * user chose in the mic menu (when still plugged in), else a headset or USB mic
 * rather than the laptop's built-in one (the browser's default can be either).
 */
async function preferredMic(
  pub: LocalTrackPublication,
  savedId: string | undefined
): Promise<MediaDeviceInfo | undefined> {
  const devices = (await Room.getLocalDevices('audioinput')).filter(
    (d) => d.deviceId !== 'default' && d.deviceId !== 'communications'
  );
  const track = pub.track?.mediaStreamTrack;
  const currentId = track?.getSettings().deviceId;
  const saved = devices.find((d) => savedId && savedId !== 'default' && d.deviceId === savedId);
  let target = saved;
  if (!target && BUILT_IN_MIC.test(track?.label ?? '')) {
    target = devices.find((d) => !BUILT_IN_MIC.test(d.label) && !NOT_A_MIC.test(d.label));
  }
  return target && target.deviceId !== currentId ? target : undefined;
}

export function useMicWatchdog() {
  const room = useRoomContext();
  const { isConnected } = useSessionContext();
  const { t } = useUiLanguage();
  const savedMicId = usePersistentUserChoices().userChoices.audioDeviceId;

  useEffect(() => {
    if (!isConnected) return;
    const me = room.localParticipant;
    const log = (message: string) => {
      me.publishData(new TextEncoder().encode(message), {
        reliable: true,
        topic: CLIENT_LOG_TOPIC,
      }).catch(() => {});
    };
    const label = (pub?: TrackPublication) =>
      pub?.track?.mediaStreamTrack?.label || 'unknown device';

    const onPublished = async (pub?: LocalTrackPublication) => {
      if (pub?.source !== Track.Source.Microphone) return;
      try {
        const better = await preferredMic(pub, savedMicId);
        if (better) {
          await room.switchActiveDevice('audioinput', better.deviceId);
          log(`microphone switched to ${better.label}`);
        }
      } catch (error) {
        log(`could not choose the microphone: ${error}`);
      }
      log(`microphone in use: ${label(me.getTrackPublication(Track.Source.Microphone))}`);
    };

    const reopenedAt: number[] = [];
    let reopening = false;
    const onMuted = async (pub: TrackPublication) => {
      if (pub.source !== Track.Source.Microphone || reopening) return;
      if (Date.now() - userToggledAt < 3_000) return; // the user pressed the mic button
      const now = Date.now();
      while (reopenedAt.length && now - reopenedAt[0] > 60_000) reopenedAt.shift();
      if (reopenedAt.length >= MAX_REOPENS_PER_MINUTE) {
        log('microphone keeps stopping; not reopening it again for a minute');
        toastAlert({
          title: t('micLostTitle'),
          description: t('micLostBody'),
          warning: true,
          sticky: true,
        });
        return;
      }
      reopenedAt.push(now);
      reopening = true;
      log(`microphone muted without the mic button (${label(pub)}); reopening it`);
      try {
        await new Promise((resolve) => setTimeout(resolve, 1_000)); // let the device settle
        await (pub as LocalTrackPublication).track?.restartTrack({ deviceId: 'default' });
        await me.setMicrophoneEnabled(true);
        log(`microphone back: ${label(me.getTrackPublication(Track.Source.Microphone))}`);
      } catch (error) {
        log(`microphone could not be reopened: ${error}`);
        toastAlert({
          title: t('micLostTitle'),
          description: t('micLostBody'),
          warning: true,
          sticky: true,
        });
      } finally {
        reopening = false;
      }
    };

    // A mic published before this effect ran
    onPublished(me.getTrackPublication(Track.Source.Microphone) as LocalTrackPublication);
    me.on(ParticipantEvent.LocalTrackPublished, onPublished);
    me.on(ParticipantEvent.TrackMuted, onMuted);
    return () => {
      me.off(ParticipantEvent.LocalTrackPublished, onPublished);
      me.off(ParticipantEvent.TrackMuted, onMuted);
    };
  }, [room, isConnected, t, savedMicId]);
}
