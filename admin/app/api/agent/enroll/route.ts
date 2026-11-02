import { fail, readJson, respond } from '@/lib/api';
import { enroll } from '@/lib/fleet';

// A workstation's first contact: its license code gets it its own key
export async function POST(request: Request) {
  return respond(async () => (await enroll(await readJson(request))) ?? fail('The license code is not valid.', 403));
}
