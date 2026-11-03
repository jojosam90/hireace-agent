// Postgres on Vercel (DATABASE_URL), or a local database file on this PC. Same SQL for both.

import { mkdir } from 'node:fs/promises';

export interface Db {
  query<T = Record<string, unknown>>(sql: string, params?: unknown[]): Promise<T[]>;
}

const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS devices (
    id text PRIMARY KEY,
    token_hash text NOT NULL UNIQUE,
    license text NOT NULL,
    hostname text NOT NULL DEFAULT '',
    windows_user text NOT NULL DEFAULT '',
    agent_name text NOT NULL DEFAULT '',
    label text NOT NULL DEFAULT '',
    version text NOT NULL DEFAULT '',
    active boolean NOT NULL DEFAULT true,
    enrolled_at double precision NOT NULL,
    last_seen double precision NOT NULL,
    part_gatekeeper boolean NOT NULL DEFAULT false,
    part_agent boolean NOT NULL DEFAULT false,
    part_web boolean NOT NULL DEFAULT false,
    in_call boolean NOT NULL DEFAULT false,
    uptime_seconds double precision,
    memory_free_mb double precision,
    memory_total_mb double precision,
    disk_free_gb double precision,
    monthly_limit_usd double precision
  )`,
  `CREATE TABLE IF NOT EXISTS releases (
    id text PRIMARY KEY,
    version text NOT NULL UNIQUE,
    url text NOT NULL,
    sha256 text NOT NULL,
    signature text NOT NULL,
    notes text NOT NULL DEFAULT '',
    size_bytes double precision NOT NULL DEFAULT 0,
    published_at double precision NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS commands (
    id text PRIMARY KEY,
    device_id text NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    type text NOT NULL,
    release_id text REFERENCES releases(id) ON DELETE SET NULL,
    status text NOT NULL,
    detail text NOT NULL DEFAULT '',
    created_by text NOT NULL,
    created_at double precision NOT NULL,
    updated_at double precision NOT NULL,
    expires_at double precision NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS commands_by_device ON commands (device_id, created_at DESC)`,
  `CREATE TABLE IF NOT EXISTS usage_daily (
    device_id text NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    day text NOT NULL,
    model text NOT NULL,
    responses double precision NOT NULL DEFAULT 0,
    in_text double precision NOT NULL DEFAULT 0,
    in_audio double precision NOT NULL DEFAULT 0,
    in_image double precision NOT NULL DEFAULT 0,
    cached_text double precision NOT NULL DEFAULT 0,
    cached_audio double precision NOT NULL DEFAULT 0,
    out_text double precision NOT NULL DEFAULT 0,
    out_audio double precision NOT NULL DEFAULT 0,
    cost_usd double precision NOT NULL DEFAULT 0,
    PRIMARY KEY (device_id, day, model)
  )`,
  `CREATE INDEX IF NOT EXISTS usage_by_day ON usage_daily (day)`,
  `CREATE TABLE IF NOT EXISTS usage_batches (
    batch_id text NOT NULL,
    device_id text NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    received_at double precision NOT NULL,
    PRIMARY KEY (device_id, batch_id)
  )`,
  `CREATE TABLE IF NOT EXISTS settings (key text PRIMARY KEY, value text NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS activity (
    id text PRIMARY KEY,
    at double precision NOT NULL,
    actor text NOT NULL,
    action text NOT NULL,
    device_id text,
    detail text NOT NULL DEFAULT ''
  )`,
  `CREATE INDEX IF NOT EXISTS activity_by_time ON activity (at DESC)`,
  `CREATE TABLE IF NOT EXISTS alerts (
    id text PRIMARY KEY,
    scope text NOT NULL,
    level double precision NOT NULL,
    severity text NOT NULL,
    title text NOT NULL,
    detail text NOT NULL DEFAULT '',
    device_id text,
    created_at double precision NOT NULL,
    acknowledged_at double precision,
    acknowledged_by text,
    emailed_at double precision,
    email_error text NOT NULL DEFAULT '',
    UNIQUE (scope, level)
  )`,
  `CREATE TABLE IF NOT EXISTS login_failures (key text NOT NULL, at double precision NOT NULL)`,
];

async function connect(): Promise<Db> {
  const url = process.env.DATABASE_URL;
  let db: Db;
  if (url) {
    const { neon } = await import('@neondatabase/serverless');
    const sql = neon(url);
    db = { query: async (text, params = []) => (await sql.query(text, params)) as never };
  } else {
    const { PGlite } = await import('@electric-sql/pglite');
    // Vercel has no lasting disk: without DATABASE_URL sign-in works, but data lasts only as long as the server
    const folder = process.env.VERCEL ? 'memory://' : (process.env.ADMIN_DATA_DIR ?? '.data/pglite');
    // It makes only its own last folder, not the ones above
    if (!folder.includes('://')) await mkdir(folder, { recursive: true });
    const pg = new PGlite(folder);
    db = { query: async (text, params = []) => (await pg.query(text, params)).rows as never };
  }
  for (const statement of SCHEMA) await db.query(statement);
  return db;
}

// Kept on globalThis: the dev server reloads modules, and the local database allows one opening
const holder = globalThis as unknown as { hireaceDb?: Promise<Db> };

export function getDb(): Promise<Db> {
  holder.hireaceDb ??= connect().catch((error) => {
    holder.hireaceDb = undefined;
    throw error;
  });
  return holder.hireaceDb;
}

/** Tests only: start again with a new empty database. */
export function resetDbForTests() {
  holder.hireaceDb = undefined;
}
