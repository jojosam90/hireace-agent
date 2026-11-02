import { respond } from '@/lib/api';
import { listReleases } from '@/lib/fleet';

export const dynamic = 'force-dynamic';

export async function GET() {
  return respond(async () => ({ releases: await listReleases() }));
}
