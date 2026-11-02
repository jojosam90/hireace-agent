import { currentAdmin } from '@/lib/auth';
import { fail, readJson, respond } from '@/lib/api';
import { cancelCommand, queueCommand, setActive } from '@/lib/fleet';

// Orders for one or many workstations: restart, install a release, deactivate, activate
export async function POST(request: Request) {
  return respond(async () => {
    const body = await readJson(request);
    const ids = Array.isArray(body.deviceIds) ? body.deviceIds.map(String) : [];
    if (!ids.length) return fail('Choose at least one workstation.');
    const admin = await currentAdmin();
    if (body.type === 'restart' || body.type === 'update') {
      const release = typeof body.releaseId === 'string' ? body.releaseId : null;
      return queueCommand(ids, body.type, admin, release);
    }
    if (body.type === 'deactivate' || body.type === 'activate') {
      for (const id of ids) await setActive(id, body.type === 'activate', admin);
      return { queued: ids.length, version: null };
    }
    return fail('Unknown order.');
  });
}

export async function DELETE(request: Request) {
  return respond(async () => {
    const id = new URL(request.url).searchParams.get('id') ?? '';
    return { cancelled: await cancelCommand(id, await currentAdmin()) };
  });
}
