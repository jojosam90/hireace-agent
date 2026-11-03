import { acknowledgeAlerts, listAlerts } from '@/lib/alerts';
import { readJson, respond } from '@/lib/api';
import { currentAdmin } from '@/lib/auth';

export const dynamic = 'force-dynamic';

export async function GET() {
  return respond(listAlerts);
}

// { id } acknowledges one; no id acknowledges all of them
export async function PATCH(request: Request) {
  return respond(async () => {
    const { id } = await readJson(request);
    await acknowledgeAlerts(typeof id === 'string' ? id : null, await currentAdmin());
    return { ok: true };
  });
}
