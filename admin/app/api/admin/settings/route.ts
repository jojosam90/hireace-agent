import { currentAdmin } from '@/lib/auth';
import { readJson, respond } from '@/lib/api';
import { logActivity } from '@/lib/fleet';
import { getSettings, saveSettings, type PortalSettings } from '@/lib/settings';

export const dynamic = 'force-dynamic';

export async function GET() {
  return respond(getSettings);
}

export async function PUT(request: Request) {
  return respond(async () => {
    const errors = await saveSettings((await readJson(request)) as unknown as PortalSettings);
    const saved = Object.keys(errors).length === 0;
    if (saved) await logActivity(await currentAdmin(), 'Changed the limits and settings', null);
    return { saved, errors };
  });
}
