// Prints the value for ADMIN_PASSWORD_HASH: node scripts/hash-password.mjs "the password"
import { randomBytes, scryptSync } from 'node:crypto';

const password = process.argv[2];
if (!password || password.length < 12) {
  console.error('Give a password of at least 12 characters.');
  process.exit(1);
}
const salt = randomBytes(16).toString('hex');
console.log(`${salt}:${scryptSync(password, salt, 64).toString('hex')}`);
