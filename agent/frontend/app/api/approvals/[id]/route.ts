import { NextResponse } from 'next/server';
import { gatekeeperConfigured, gatekeeperFetch } from '@/lib/gatekeeper';

export const revalidate = 0;

// Approve or deny one pending action from the web app
export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!gatekeeperConfigured()) {
    return NextResponse.json({ status: 'unavailable' }, { status: 503 });
  }
  const { id } = await params;
  const { decision } = await req.json();
  if (decision !== 'approve' && decision !== 'deny') {
    return NextResponse.json({ error: 'decision must be approve or deny' }, { status: 400 });
  }
  const res = await gatekeeperFetch(`/v1/approvals/${encodeURIComponent(id)}`, {
    method: 'POST',
    body: JSON.stringify({ decision, channel: 'web' }),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
