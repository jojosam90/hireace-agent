// Works in middleware too (no Node-only imports)
import { jwtVerify, SignJWT } from 'jose';

export const SESSION_COOKIE = 'hireace_admin';
export const SESSION_HOURS = 12;

const secret = () => new TextEncoder().encode(process.env.SESSION_SECRET ?? '');

export async function signSession(username: string): Promise<string> {
  return new SignJWT({})
    .setProtectedHeader({ alg: 'HS256' })
    .setSubject(username)
    .setIssuedAt()
    .setExpirationTime(`${SESSION_HOURS}h`)
    .sign(secret());
}

export async function verifySession(token: string | undefined): Promise<string | null> {
  if (!token || !process.env.SESSION_SECRET) return null;
  try {
    const { payload } = await jwtVerify(token, secret(), { algorithms: ['HS256'] });
    return payload.sub ?? null;
  } catch {
    return null;
  }
}
