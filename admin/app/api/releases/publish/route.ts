import { timingSafeEqual } from 'node:crypto';
import { bearer, fail, readJson, respond } from '@/lib/api';
import { addRelease } from '@/lib/fleet';

function keyIsRight(given: string): boolean {
  const key = process.env.RELEASE_PUBLISH_KEY;
  if (!key) return false;
  const a = Buffer.from(given);
  const b = Buffer.from(key);
  return a.length === b.length && timingSafeEqual(a, b);
}

// installer/publish-release.ps1. This key only lists a release: workstations install only
// what is signed with the private key, which is not on this server.
export async function POST(request: Request) {
  return respond(async () => {
    if (!keyIsRight(bearer(request))) return fail('Wrong publish key.', 401);
    const release = await addRelease(await readJson(request), 'release script');
    return { id: release.id, version: release.version };
  });
}
