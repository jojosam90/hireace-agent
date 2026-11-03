import { NextResponse } from 'next/server';
import { DEVICE_COOKIE } from '@/lib/remember';
import { SESSION_COOKIE } from '@/lib/session';

// Signing out also ends this device being remembered: the next login needs the password
export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete(SESSION_COOKIE);
  response.cookies.delete(DEVICE_COOKIE);
  return response;
}
