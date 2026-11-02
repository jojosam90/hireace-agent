import { NextResponse } from 'next/server';
import { AccessToken } from 'livekit-server-sdk';
import { fromThisPc, gatekeeperConfigured, gatekeeperFetch } from '@/lib/gatekeeper';

export const revalidate = 0;

// The call running on this PC's agent (e.g. started from the phone), with a token for
// the panel to follow it. It cannot publish and receives no audio, so it cannot echo
// into the call; the conversation's text still reaches it. (Not `hidden`: LiveKit then
// delivers no text to it in a browser.)
export async function GET(req: Request) {
  const { LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET } = process.env;
  if (
    !fromThisPc(req) ||
    !gatekeeperConfigured() ||
    !LIVEKIT_URL ||
    !LIVEKIT_API_KEY ||
    !LIVEKIT_API_SECRET
  ) {
    return NextResponse.json({ room: null });
  }
  try {
    const res = await gatekeeperFetch('/v1/calls', { signal: AbortSignal.timeout(2000) });
    const { room } = (await res.json()) as { room: string | null };
    if (!room) return NextResponse.json({ room: null });

    const at = new AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET, {
      identity: `panel_mirror_${crypto.randomUUID().slice(0, 8)}`,
      ttl: '5m', // to join; staying in the call needs no new token
    });
    at.addGrant({
      room,
      roomJoin: true,
      canPublish: false,
      canPublishData: false,
      canSubscribe: false,
    });
    return NextResponse.json(
      { room, url: LIVEKIT_URL, token: await at.toJwt() },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  } catch {
    return NextResponse.json({ room: null });
  }
}
