import { type NextRequest, NextResponse } from 'next/server';
import { ACCESS_COOKIE, accessCode, accessToken } from '@/lib/access';
import { PC_COOKIE, validPc } from '@/lib/phone-link';

// Anyone with the link could otherwise start a call that controls the PC
async function checkAccess(req: NextRequest) {
  const code = accessCode();
  const { pathname } = req.nextUrl;
  if (!code || pathname === '/login' || pathname === '/api/login') {
    return NextResponse.next();
  }
  if (req.cookies.get(ACCESS_COOKIE)?.value === (await accessToken(code))) {
    return NextResponse.next();
  }
  if (pathname.startsWith('/api/')) {
    return NextResponse.json({ error: 'Access code needed' }, { status: 401 });
  }
  return NextResponse.redirect(new URL('/login', req.url));
}

export async function middleware(req: NextRequest) {
  const res = await checkAccess(req);
  // Opened with a PC's phone link: remember that PC on this phone
  const pc = validPc(req.nextUrl.searchParams.get('pc'));
  if (pc) {
    res.cookies.set(PC_COOKIE, pc, {
      httpOnly: true,
      secure: true,
      sameSite: 'lax',
      maxAge: 60 * 60 * 24 * 365,
      path: '/',
    });
  }
  return res;
}

export const config = {
  // Not the app's icons and install manifest: phones fetch them without the access
  // cookie, and an app whose manifest redirects to /login cannot be installed
  matcher: [
    '/((?!_next/static|_next/image|icon.svg|favicon.ico|apple-icon.png|manifest.webmanifest|icons/).*)',
  ],
};
