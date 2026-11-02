import { cookies, headers } from 'next/headers';
import { App } from '@/components/app/app';
import { PC_COOKIE, validPc } from '@/lib/phone-link';
import { getAppConfig } from '@/lib/utils';

export default async function Page({ searchParams }: { searchParams: Promise<{ pc?: string }> }) {
  const hdrs = await headers();
  const appConfig = await getAppConfig(hdrs);
  // On the PC: its own agent (AGENT_NAME). On the shared site: the PC from the
  // phone link, or the one this phone opened last.
  const pc = validPc((await searchParams).pc) ?? validPc((await cookies()).get(PC_COOKIE)?.value);

  return (
    <App
      appConfig={{
        ...appConfig,
        agentName: appConfig.agentName ?? pc,
        phoneSiteUrl: process.env.PHONE_SITE_URL || undefined,
      }}
    />
  );
}
