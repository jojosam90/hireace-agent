import { sendTestEmail } from '@/lib/alerts';
import { fail, respond } from '@/lib/api';

export async function POST() {
  return respond(async () => {
    const problem = await sendTestEmail();
    return problem ? fail(problem) : { sent: true };
  });
}
