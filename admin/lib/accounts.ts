// Who can sign in. ADMIN_ACCOUNTS is a JSON list, each with their own password hash
// (pnpm hash-password); without it, the one account in ADMIN_USERNAME and ADMIN_PASSWORD_HASH.

export interface Account {
  username: string;
  name: string;
  role: string;
  passwordHash: string;
  /** Sent to anyone who opens the login page, to fill the password in: see .env.example */
  prefillPassword?: string;
}

export function loadAccounts(): Account[] {
  const list = process.env.ADMIN_ACCOUNTS;
  if (list?.trim()) {
    try {
      const parsed = JSON.parse(list) as Partial<Account>[];
      const valid = parsed.filter((item) => item.username && item.passwordHash);
      if (valid.length) {
        return valid.map((item) => ({
          username: String(item.username),
          name: String(item.name || item.username),
          role: String(item.role || 'Admin'),
          passwordHash: String(item.passwordHash),
          ...(item.prefillPassword ? { prefillPassword: String(item.prefillPassword) } : {}),
        }));
      }
    } catch {
      console.error('ADMIN_ACCOUNTS is not valid JSON: using ADMIN_USERNAME instead.');
    }
  }
  const username = process.env.ADMIN_USERNAME;
  const passwordHash = process.env.ADMIN_PASSWORD_HASH;
  if (!username || !passwordHash) return [];
  const prefillPassword = process.env.ADMIN_PREFILL_PASSWORD;
  return [{ username, name: 'Administrator', role: 'Admin', passwordHash, ...(prefillPassword ? { prefillPassword } : {}) }];
}

/** What the login page shows, to anyone: never the password hashes. */
export function publicAccounts() {
  return loadAccounts().map(({ username, name, role, prefillPassword }) => ({
    username,
    name,
    role,
    ...(prefillPassword ? { prefillPassword } : {}),
  }));
}

/** "Mei Ling Wong" -> "MW" */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return '?';
  const first = words[0][0];
  const last = words.length > 1 ? words[words.length - 1][0] : '';
  return (first + last).toUpperCase();
}
