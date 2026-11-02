import { respond } from '@/lib/api';
import { listActivity } from '@/lib/fleet';

export const dynamic = 'force-dynamic';

export async function GET() {
  return respond(async () => ({ activity: await listActivity() }));
}
