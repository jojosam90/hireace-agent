import { createHmac, timingSafeEqual } from 'node:crypto';

// The same check as installer/license.ps1: the last 4 characters of a code are worked out
// from the first 8 with the secret key
const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';

export function formatLicense(code: string): string {
  const plain = code.toUpperCase().replace(/[\s-]/g, '');
  if (!/^[A-Z0-9]{12}$/.test(plain)) return '';
  return `${plain.slice(0, 4)}-${plain.slice(4, 8)}-${plain.slice(8)}`;
}

export function licenseIsValid(code: string, secret: string | undefined): boolean {
  const formatted = formatLicense(code);
  if (!formatted || !secret?.trim()) return false;
  const plain = formatted.replace(/-/g, '');
  const hash = createHmac('sha256', secret.trim()).update(plain.slice(0, 8), 'ascii').digest();
  const check = [0, 1, 2, 3].map((i) => ALPHABET[hash[i] % ALPHABET.length]).join('');
  return timingSafeEqual(Buffer.from(check), Buffer.from(plain.slice(8)));
}
