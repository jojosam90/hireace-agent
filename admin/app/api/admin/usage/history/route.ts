import { respond } from '@/lib/api';
import { spendPeriods, usageHistory } from '@/lib/fleet';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  return respond(async () => {
    const query = new URL(request.url).searchParams;
    const days = query.get('days') === '30' ? 30 : 7;
    const page = Math.max(0, Math.min(52, Number(query.get('page')) || 0));
    const [history, periods] = await Promise.all([usageHistory(days, page), spendPeriods()]);
    return { ...history, ...periods };
  });
}
