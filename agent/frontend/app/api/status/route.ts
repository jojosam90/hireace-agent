import { NextResponse } from 'next/server';
import { gatekeeperConfigured, gatekeeperFetch } from '@/lib/gatekeeper';

export const revalidate = 0;

// Is HireAce running on this PC (its gatekeeper answers)? "unknown" where the
// gatekeeper is out of reach (the phone site): there the call shows it instead.
export async function GET() {
  if (!gatekeeperConfigured()) {
    return NextResponse.json({ state: 'unknown' });
  }
  try {
    const res = await gatekeeperFetch('/healthz', { signal: AbortSignal.timeout(2000) });
    return NextResponse.json({ state: res.ok ? 'online' : 'offline' });
  } catch {
    return NextResponse.json({ state: 'offline' });
  }
}
