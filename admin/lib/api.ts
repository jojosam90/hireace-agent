import { NextResponse } from 'next/server';
import { FleetError } from './fleet';

export const fail = (error: string, status = 400) => NextResponse.json({ error }, { status });

/** Runs a route: an expected refusal is shown to the admin, anything else is logged. */
export async function respond(run: () => Promise<unknown>) {
  try {
    const result = await run();
    return result instanceof Response ? result : NextResponse.json(result);
  } catch (error) {
    if (error instanceof FleetError) return fail(error.message);
    console.error(error);
    return fail('Something went wrong on the server.', 500);
  }
}

export async function readJson(request: Request): Promise<Record<string, unknown>> {
  try {
    const body = await request.json();
    return body && typeof body === 'object' ? body : {};
  } catch {
    return {};
  }
}

export function bearer(request: Request): string {
  return (request.headers.get('authorization') ?? '').replace(/^Bearer\s+/i, '');
}
