import { currentAdmin } from '@/lib/auth';
import { fail, readJson, respond } from '@/lib/api';
import {
  dailyCost,
  deviceHistory,
  latestRelease,
  listDevices,
  removeDevice,
  setActive,
  updateDevice,
} from '@/lib/fleet';

export const dynamic = 'force-dynamic';

type Context = { params: Promise<{ id: string }> };

export async function GET(_: Request, { params }: Context) {
  return respond(async () => {
    const { id } = await params;
    const device = (await listDevices()).find((row) => row.id === id);
    if (!device) return fail('That workstation is not listed.', 404);
    const [history, daily, latest] = await Promise.all([deviceHistory(id), dailyCost(id), latestRelease()]);
    return { device, history, daily, latestVersion: latest?.version ?? null };
  });
}

export async function PATCH(request: Request, { params }: Context) {
  return respond(async () => {
    const { id } = await params;
    const body = await readJson(request);
    const admin = await currentAdmin();
    if (typeof body.active === 'boolean') await setActive(id, body.active, admin);
    await updateDevice(id, { label: body.label, monthlyLimitUsd: body.monthlyLimitUsd }, admin);
    return { ok: true };
  });
}

export async function DELETE(_: Request, { params }: Context) {
  return respond(async () => {
    const { id } = await params;
    return { removed: await removeDevice(id, await currentAdmin()) };
  });
}
