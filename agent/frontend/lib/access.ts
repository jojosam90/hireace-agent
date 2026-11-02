// Access code for a public deployment (e.g. Vercel): set HIREACE_ACCESS_CODE and every
// page and API route asks for it once per device. Unset on the PC itself.

export const ACCESS_COOKIE = 'hireace-access';

export function accessCode(): string | undefined {
  return process.env.HIREACE_ACCESS_CODE || undefined;
}

/** What the cookie holds: a hash of the code, never the code itself. */
export async function accessToken(code: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`hireace:${code}`));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
