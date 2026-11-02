import { NextResponse } from 'next/server';
import { fromThisPc, gatekeeperConfigured, gatekeeperFetch } from '@/lib/gatekeeper';

export const revalidate = 0;

// The Settings page: values in effect (secrets masked), and saving changes. Kept by
// the gatekeeper on this PC, and changed only on the PC itself.
export async function GET(req: Request) {
  if (!fromThisPc(req)) {
    return NextResponse.json({ error: 'pc_only' }, { status: 403 });
  }
  if (!gatekeeperConfigured()) {
    return NextResponse.json({ error: 'unavailable' }, { status: 503 });
  }
  try {
    const res = await gatekeeperFetch('/v1/settings');
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return NextResponse.json({ error: 'unavailable' }, { status: 502 });
  }
}

export async function POST(req: Request) {
  if (!fromThisPc(req)) {
    return NextResponse.json({ error: 'pc_only' }, { status: 403 });
  }
  if (!gatekeeperConfigured()) {
    return NextResponse.json({ error: 'unavailable' }, { status: 503 });
  }
  const res = await gatekeeperFetch('/v1/settings', {
    method: 'POST',
    body: JSON.stringify(await req.json()),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
