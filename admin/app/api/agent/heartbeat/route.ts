import { bearer, fail, readJson, respond } from '@/lib/api';
import { heartbeat } from '@/lib/fleet';

// A workstation checking in: it says how it is, and the answer carries any orders
export async function POST(request: Request) {
  return respond(async () => (await heartbeat(bearer(request), await readJson(request))) ?? fail('Unknown key.', 401));
}
