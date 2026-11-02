import { NextResponse } from 'next/server';
import { gatekeeperConfigured, gatekeeperFetch } from '@/lib/gatekeeper';

export const revalidate = 0;

// Pending actions waiting for the user's approval
export async function GET() {
  if (!gatekeeperConfigured()) {
    return NextResponse.json([]);
  }
  try {
    const res = await gatekeeperFetch('/v1/approvals');
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return NextResponse.json([], { status: 502 });
  }
}
