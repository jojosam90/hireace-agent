import { NextResponse } from 'next/server';
import { fromThisPc, gatekeeperConfigured, gatekeeperFetch } from '@/lib/gatekeeper';

export const revalidate = 0;

// Is Gmail open and signed in in HireAce's browser, ready to send?
export async function GET(req: Request) {
  if (!fromThisPc(req)) {
    return NextResponse.json({ error: 'pc_only' }, { status: 403 });
  }
  if (!gatekeeperConfigured()) {
    return NextResponse.json({ state: 'error', email: '' });
  }
  try {
    const res = await gatekeeperFetch('/v1/gmail');
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return NextResponse.json({ state: 'error', email: '' }, { status: 502 });
  }
}
