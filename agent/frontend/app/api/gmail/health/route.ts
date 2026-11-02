import { NextResponse } from 'next/server';
import { fromThisPc, gatekeeperConfigured, gatekeeperFetch } from '@/lib/gatekeeper';

export const revalidate = 0;

// Is Gmail signed in, in any browser on this PC?
export async function GET(req: Request) {
  if (!fromThisPc(req)) {
    return NextResponse.json({ error: 'pc_only' }, { status: 403 });
  }
  if (!gatekeeperConfigured()) {
    return NextResponse.json({ error: 'unavailable' }, { status: 503 });
  }
  try {
    const res = await gatekeeperFetch('/v1/gmail/health');
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return NextResponse.json({ error: 'unavailable' }, { status: 502 });
  }
}
