import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { getDb, resetDbForTests } from '@/lib/db';

afterEach(() => {
  process.env.ADMIN_DATA_DIR = 'memory://';
  resetDbForTests();
});

describe('the local database', () => {
  it('starts on a new PC, where its folders do not exist yet', async () => {
    delete process.env.DATABASE_URL;
    process.env.ADMIN_DATA_DIR = path.join(mkdtempSync(path.join(tmpdir(), 'hireace-')), '.data', 'pglite');
    resetDbForTests();

    const db = await getDb();

    expect(await db.query('SELECT COUNT(*) AS n FROM devices')).toEqual([{ n: expect.anything() }]);
  });
});
