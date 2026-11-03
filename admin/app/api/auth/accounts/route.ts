import { NextResponse } from 'next/server';
import { publicAccounts } from '@/lib/accounts';

export const dynamic = 'force-dynamic';

// The cards on the login page: names and roles only
export async function GET() {
  return NextResponse.json({ accounts: publicAccounts() });
}
