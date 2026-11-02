import { NextResponse } from 'next/server';
import { fromThisPc, gatekeeperConfigured, gatekeeperFetch } from '@/lib/gatekeeper';

export const revalidate = 0;

const ACTIONS = new Set(['open', 'show', 'test']);

// Open a Gmail link, go to the Gmail tab already open, or send a test email (on the PC
// itself only)
export async function POST(req: Request, { params }: { params: Promise<{ action: string }> }) {
  const { action } = await params;
  if (!ACTIONS.has(action)) {
    return NextResponse.json({ error: 'Unknown action' }, { status: 404 });
  }
  if (!fromThisPc(req)) {
    return NextResponse.json({ error: 'pc_only' }, { status: 403 });
  }
  if (!gatekeeperConfigured()) {
    return NextResponse.json({ error: 'unavailable' }, { status: 503 });
  }
  const res = await gatekeeperFetch(`/v1/gmail/${action}`, {
    method: 'POST',
    // test: { to }; open: optionally { link } (a Gmail link to show there)
    body: (await req.text()) || '{}',
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
