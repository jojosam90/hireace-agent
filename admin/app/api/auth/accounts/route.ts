import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';
import { publicAccounts } from '@/lib/accounts';
import { DEVICE_COOKIE, rememberedAccounts } from '@/lib/remember';

export const dynamic = 'force-dynamic';

// The cards on the login page: names and roles only, and which this device remembers
export async function GET() {
  const store = await cookies();
  const remembered = await rememberedAccounts(store.get(DEVICE_COOKIE)?.value);
  return NextResponse.json({
    accounts: publicAccounts().map((account) => ({ ...account, remembered: remembered.includes(account.username) })),
  });
}
