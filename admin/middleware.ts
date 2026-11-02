import { NextResponse, type NextRequest } from 'next/server';
import { SESSION_COOKIE, verifySession } from '@/lib/session';

// Everything needs a signed-in admin, except what workstations and the release script
// call (they bring their own keys) and the sign-in itself
const OPEN = ['/login', '/api/auth/login', '/api/agent/', '/api/releases/publish'];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (OPEN.some((path) => pathname === path || (path.endsWith('/') && pathname.startsWith(path)))) {
    return NextResponse.next();
  }
  const admin = await verifySession(request.cookies.get(SESSION_COOKIE)?.value);
  const isApi = pathname.startsWith('/api/');
  if (!admin) {
    if (isApi) return NextResponse.json({ error: 'Sign in first.' }, { status: 401 });
    return NextResponse.redirect(new URL('/login', request.url));
  }
  // Changes only from the portal's own pages
  if (isApi && request.method !== 'GET') {
    const origin = request.headers.get('origin');
    if (!origin || new URL(origin).host !== request.headers.get('host')) {
      return NextResponse.json({ error: 'Not allowed from another site.' }, { status: 403 });
    }
  }
  return NextResponse.next();
}

export const config = { matcher: ['/((?!_next/|logo\.png).*)'] };
