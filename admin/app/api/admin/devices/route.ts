import { respond } from '@/lib/api';
import { latestRelease, listDevices } from '@/lib/fleet';
import { getSettings } from '@/lib/settings';

export const dynamic = 'force-dynamic';

export async function GET() {
  return respond(async () => {
    const [devices, latest, settings] = await Promise.all([listDevices(), latestRelease(), getSettings()]);
    return {
      devices,
      latestVersion: latest?.version ?? null,
      heartbeatSeconds: settings.heartbeatSeconds,
      offlineAfterSeconds: settings.offlineAfterSeconds,
    };
  });
}
