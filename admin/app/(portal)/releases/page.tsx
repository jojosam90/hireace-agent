'use client';

import { PackageCheck, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { OrderDialog } from '@/components/orders';
import { Badge, Button, Card, Empty, Loading, Page, Problem } from '@/components/ui';
import { usePoll } from '@/lib/client';
import { ago, dateTime } from '@/lib/format';
import type { DevicesData, ReleaseView } from '@/lib/types';

export default function ReleasesPage() {
  const releases = usePoll<{ releases: ReleaseView[] }>('/api/admin/releases');
  const fleet = usePoll<DevicesData>('/api/admin/devices');
  const [chosen, setChosen] = useState<ReleaseView | null>(null);
  const [message, setMessage] = useState('');

  if (!releases.data || !fleet.data) {
    return releases.error || fleet.error ? <Problem>{releases.error || fleet.error}</Problem> : <Loading />;
  }

  const active = fleet.data.devices.filter((device) => device.active);
  const updating = active.filter((device) => device.state === 'updating').length;
  const needing = (release: ReleaseView) =>
    active.filter((device) => device.version !== release.version && device.state !== 'updating');

  return (
    <Page title="Releases" intro="New versions of HireAce, published from the developer's PC with installer\publish-release.ps1.">
      <p className="bg-brand-50 text-brand-700 mb-4 flex items-start gap-2 rounded-xl px-4 py-3 text-sm font-semibold">
        <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
        Workstations install only what is signed with your private release key, which is not on this server. If anyone gets into this
        portal, they still cannot put their own code on your PCs.
      </p>
      {message && (
        <p role="status" className="bg-brand-50 text-brand-700 mb-3 rounded-xl px-4 py-2.5 text-sm font-bold">
          {message}
        </p>
      )}

      {releases.data.releases.length === 0 ? (
        <Card>
          <Empty icon={PackageCheck} title="No releases yet">
            Publish the first one from the developer&apos;s PC. It then appears here, ready to install.
          </Empty>
        </Card>
      ) : (
        <ul className="space-y-3">
          {releases.data.releases.map((release) => {
            const count = needing(release).length;
            return (
              <li key={release.id}>
                <Card>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-lg font-extrabold break-all">{release.version}</h2>
                        {release.isLatest && <Badge tone="good">Latest</Badge>}
                      </div>
                      <p className="text-muted text-sm" title={dateTime(release.publishedAt)}>
                        Published {ago(release.publishedAt)} · on {release.installedOn} of {active.length} workstations
                        {release.sizeBytes > 0 && ` · ${(release.sizeBytes / 1_048_576).toFixed(1)} MB`}
                      </p>
                      {release.notes && <p className="mt-2 text-sm whitespace-pre-line">{release.notes}</p>}
                    </div>
                    <Button
                      kind="soft"
                      icon={PackageCheck}
                      disabled={count === 0}
                      onClick={() => setChosen(release)}
                      className="w-full sm:w-auto"
                    >
                      {updating > 0 && count === 0
                        ? 'Updating now'
                        : count === 0
                          ? 'All up to date'
                          : `Install on ${count} workstation${count === 1 ? '' : 's'}`}
                    </Button>
                  </div>
                </Card>
              </li>
            );
          })}
        </ul>
      )}

      {chosen && (
        <OrderDialog
          type="update"
          deviceIds={needing(chosen).map((device) => device.id)}
          name={`${needing(chosen).length} workstation${needing(chosen).length === 1 ? '' : 's'}`}
          version={chosen.version}
          releaseId={chosen.id}
          onClose={() => setChosen(null)}
          onDone={(text) => {
            setMessage(text);
            setChosen(null);
            fleet.reload();
          }}
        />
      )}
    </Page>
  );
}
