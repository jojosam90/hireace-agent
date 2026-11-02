'use client';

import { Activity } from 'lucide-react';
import Link from 'next/link';
import { Card, Empty, Loading, Page, Problem } from '@/components/ui';
import { usePoll } from '@/lib/client';
import { dateTime } from '@/lib/format';
import type { ActivityRow } from '@/lib/types';

export default function ActivityPage() {
  const { data, error } = usePoll<{ activity: ActivityRow[] }>('/api/admin/activity');
  if (!data) return error ? <Problem>{error}</Problem> : <Loading />;

  return (
    <Page fill title="Activity" intro="Everything done from this portal, who did it, and how it ended. The last 100 events.">
      <Card className="scroll-thin min-h-0 flex-initial overflow-y-auto">
        {data.activity.length === 0 ? (
          <Empty icon={Activity} title="Nothing yet" />
        ) : (
          <ul className="divide-line divide-y text-sm">
            {data.activity.map((row) => (
              <li key={row.id} className="flex flex-col gap-0.5 py-3 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
                <span className="min-w-0 break-words">
                  <strong>{row.action}</strong>
                  {row.device_id && row.device && (
                    <>
                      {' · '}
                      <Link href={`/workstations/${row.device_id}`} className="text-brand-700 font-bold">
                        {row.device}
                      </Link>
                    </>
                  )}
                  {row.detail && row.detail !== row.device && <span className="text-muted"> · {row.detail}</span>}
                </span>
                <span className="text-muted shrink-0 text-xs">
                  {row.actor} · {dateTime(row.at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </Page>
  );
}
