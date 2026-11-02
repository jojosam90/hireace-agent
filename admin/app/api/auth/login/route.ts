import { NextResponse } from 'next/server';
import { fail, readJson, respond } from '@/lib/api';
import { login } from '@/lib/auth';
import { SESSION_COOKIE, SESSION_HOURS, signSession } from '@/lib/session';

const REFUSALS = {
  wrong: ['The username or password is not right.', 401],
  locked: ['Too many tries. Wait 15 minutes and try again.', 429],
  not_set_up: ['Sign-in is not set up on the server yet.', 503],
} as const;

export async function POST(request: Request) {
  return respond(async () => {
    const body = await readJson(request);
    const username = String(body.username ?? '');
    const address = request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() || 'local';
    const result = await login(username, String(body.password ?? ''), address);
    if (result !== 'ok') return fail(REFUSALS[result][0], REFUSALS[result][1]);

    const response = NextResponse.json({ ok: true });
    response.cookies.set(SESSION_COOKIE, await signSession(username), {
      httpOnly: true,
      sameSite: 'lax',
      secure: (request.headers.get('x-forwarded-proto') ?? new URL(request.url).protocol).startsWith('https'),
      path: '/',
      maxAge: SESSION_HOURS * 3600,
    });
    return response;
  });
}
