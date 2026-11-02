import { respond } from '@/lib/api';
import { listDevices, usageSummary } from '@/lib/fleet';
import { billedThisMonth } from '@/lib/openai-billing';

export const dynamic = 'force-dynamic';

export async function GET() {
  return respond(async () => {
    const [summary, devices, billed] = await Promise.all([usageSummary(), listDevices(), billedThisMonth()]);
    return {
      ...summary,
      billed,
      adminKeySet: Boolean(process.env.OPENAI_ADMIN_KEY),
      devices: devices
        .filter((device) => device.monthCostUsd > 0 || device.limitUsd !== null)
        .map((device) => ({
          id: device.id,
          name: device.name,
          cost: device.monthCostUsd,
          limit: device.limitUsd,
        }))
        .sort((a, b) => b.cost - a.cost),
    };
  });
}
