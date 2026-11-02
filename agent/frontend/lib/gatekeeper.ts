// Server-side helper for talking to the gatekeeper service (Docker setup).
// The token stays on the server; the browser only talks to our /api routes.

/**
 * Opened on the PC itself (the panel or http://localhost:3001), not from the network.
 * Settings and the Gmail connection are changed only there, until phones are paired.
 */
export function fromThisPc(req: Request): boolean {
  const host = new URL(req.url).hostname;
  return host === 'localhost' || host === '127.0.0.1' || host === '[::1]';
}

export function gatekeeperConfigured(): boolean {
  return Boolean(process.env.GATEKEEPER_URL && process.env.GATEKEEPER_TOKEN);
}

export async function gatekeeperFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${process.env.GATEKEEPER_URL}${path}`, {
    ...init,
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      'X-Gatekeeper-Token': process.env.GATEKEEPER_TOKEN ?? '',
      ...init?.headers,
    },
  });
}
