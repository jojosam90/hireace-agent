import { NextResponse } from 'next/server';
import { ACCESS_COOKIE, accessCode, accessToken } from '@/lib/access';

// The access code form on /login: right code → remembered on this device for 30 days
export async function POST(req: Request) {
  const code = accessCode();
  const typed = String((await req.formData()).get('code') ?? '').trim();
  if (!code || (await accessToken(typed)) !== (await accessToken(code))) {
    return NextResponse.redirect(new URL('/login?wrong=1', req.url), 303);
  }
  const res = NextResponse.redirect(new URL('/', req.url), 303);
  res.cookies.set(ACCESS_COOKIE, await accessToken(code), {
    httpOnly: true,
    secure: true,
    sameSite: 'lax',
    maxAge: 60 * 60 * 24 * 30,
    path: '/',
  });
  return res;
}
