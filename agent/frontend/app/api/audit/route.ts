import { NextResponse } from 'next/server';
import { gatekeeperConfigured, gatekeeperFetch } from '@/lib/gatekeeper';

export const revalidate = 0;

// Recent gatekeeper decisions (allowed / asked / denied actions)
export async function GET() {
  if (!gatekeeperConfigured()) {
    return NextResponse.json([]);
  }
  const res = await gatekeeperFetch('/v1/audit?limit=100');
  return NextResponse.json(await res.json(), { status: res.status });
}
