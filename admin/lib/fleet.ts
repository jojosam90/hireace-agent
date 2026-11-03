// The workstations: what they report, what they are told to do, and what they cost.
// PCs behind a router cannot be reached from the internet, so nothing here calls a PC:
// each one checks in, and gets its orders in the answer.

import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { checkSpendAlerts } from './alerts';
import { getDb } from './db';
import { formatLicense, licenseIsValid } from './license';
import { getSettings, type PortalSettings, type Prices } from './settings';

const HOUR = 3_600_000;
const COMMAND_LIFETIME: Record<CommandType, number> = {
  restart: HOUR, // a restart hours later would surprise whoever is working then
  update: 7 * 24 * HOUR,
};
const STUCK_AFTER = HOUR;

export type CommandType = 'restart' | 'update';
export type CommandStatus = 'pending' | 'sent' | 'running' | 'done' | 'failed' | 'expired' | 'cancelled';
export type DeviceState = 'deactivated' | 'offline' | 'updating' | 'up' | 'partial' | 'down';

export interface DeviceRow {
  id: string;
  license: string;
  hostname: string;
  windows_user: string;
  agent_name: string;
  label: string;
  version: string;
  active: boolean;
  enrolled_at: number;
  last_seen: number;
  part_gatekeeper: boolean;
  part_agent: boolean;
  part_web: boolean;
  in_call: boolean;
  uptime_seconds: number | null;
  memory_free_mb: number | null;
  memory_total_mb: number | null;
  disk_free_gb: number | null;
  monthly_limit_usd: number | null;
}

export interface CommandRow {
  id: string;
  device_id: string;
  type: CommandType;
  release_id: string | null;
  status: CommandStatus;
  detail: string;
  created_by: string;
  created_at: number;
  updated_at: number;
  expires_at: number;
}

export interface ReleaseRow {
  id: string;
  version: string;
  url: string;
  sha256: string;
  signature: string;
  notes: string;
  size_bytes: number;
  published_at: number;
}

export interface UsageItem {
  day: string;
  model: string;
  responses?: number;
  inText?: number;
  inAudio?: number;
  inImage?: number;
  cachedText?: number;
  cachedAudio?: number;
  outText?: number;
  outAudio?: number;
}

export interface HeartbeatReport {
  hostname?: string;
  windowsUser?: string;
  agentName?: string;
  version?: string;
  parts?: { gatekeeper?: boolean; agent?: boolean; web?: boolean };
  inCall?: boolean;
  uptimeSeconds?: number;
  memoryFreeMb?: number;
  memoryTotalMb?: number;
  diskFreeGb?: number;
  usage?: { batchId: string; items: UsageItem[] };
  results?: { id: string; status: 'running' | 'done' | 'failed'; detail?: string }[];
}

const hashToken = (token: string) => createHash('sha256').update(token).digest('hex');
const text = (value: unknown, max = 200) => (typeof value === 'string' ? value.slice(0, max) : '');
const count = (value: unknown) => (typeof value === 'number' && value > 0 ? value : 0);
const numberOrNull = (value: unknown) => (typeof value === 'number' && Number.isFinite(value) ? value : null);

export const monthOf = (at: number) => new Date(at).toISOString().slice(0, 7);

export function costOf(item: UsageItem, prices: Prices): number {
  const cachedText = count(item.cachedText);
  const cachedAudio = count(item.cachedAudio);
  // OpenAI counts cached tokens inside the input totals, at a lower price
  const perMillion =
    Math.max(count(item.inText) - cachedText, 0) * prices.inText +
    cachedText * prices.cachedText +
    Math.max(count(item.inAudio) - cachedAudio, 0) * prices.inAudio +
    cachedAudio * prices.cachedAudio +
    count(item.inImage) * prices.inImage +
    count(item.outText) * prices.outText +
    count(item.outAudio) * prices.outAudio;
  return perMillion / 1_000_000;
}

export function deviceState(
  device: DeviceRow,
  settings: PortalSettings,
  updating: boolean,
  now = Date.now(),
): DeviceState {
  if (!device.active) return 'deactivated';
  if (now - device.last_seen > settings.offlineAfterSeconds * 1000) return 'offline';
  if (updating) return 'updating';
  const parts = [device.part_gatekeeper, device.part_agent, device.part_web].filter(Boolean).length;
  return parts === 3 ? 'up' : parts === 0 ? 'down' : 'partial';
}

export async function logActivity(
  actor: string,
  action: string,
  deviceId: string | null,
  detail = '',
  now = Date.now(),
) {
  const db = await getDb();
  await db.query(`INSERT INTO activity (id, at, actor, action, device_id, detail) VALUES ($1, $2, $3, $4, $5, $6)`, [
    randomUUID(),
    now,
    actor,
    action,
    deviceId,
    detail,
  ]);
}

// --- A workstation joining ---------------------------------------------------------

/** A valid license code gets a new identity. Null when the code is not valid. */
export async function enroll(body: Record<string, unknown>, now = Date.now()) {
  const license = text(body.license, 40);
  if (!licenseIsValid(license, process.env.LICENSE_SECRET)) return null;
  const db = await getDb();
  const id = randomUUID();
  const token = randomBytes(32).toString('base64url');
  await db.query(
    `INSERT INTO devices (id, token_hash, license, hostname, windows_user, agent_name, version, enrolled_at, last_seen)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
    [
      id,
      hashToken(token),
      formatLicense(license),
      text(body.hostname),
      text(body.windowsUser),
      text(body.agentName),
      text(body.version),
      now,
      now,
    ],
  );
  await logActivity('system', 'Workstation joined', id, text(body.hostname), now);
  return { deviceId: id, token };
}

// --- A workstation checking in -----------------------------------------------------

async function recordUsage(deviceId: string, usage: HeartbeatReport['usage'], prices: Prices, now: number) {
  if (!usage?.batchId || !Array.isArray(usage.items)) return false;
  const db = await getDb();
  // A batch whose answer got lost is sent again: counted once
  const fresh = await db.query(
    `INSERT INTO usage_batches (batch_id, device_id, received_at) VALUES ($1, $2, $3)
     ON CONFLICT DO NOTHING RETURNING batch_id`,
    [text(usage.batchId, 80), deviceId, now],
  );
  if (!fresh.length) return false;
  for (const item of usage.items) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(item.day ?? '')) continue;
    await db.query(
      `INSERT INTO usage_daily AS u (device_id, day, model, responses, in_text, in_audio, in_image, cached_text, cached_audio, out_text, out_audio, cost_usd)
       VALUES ($1, $2, $3, $12, $4, $5, $6, $7, $8, $9, $10, $11)
       ON CONFLICT (device_id, day, model) DO UPDATE SET
         responses = u.responses + EXCLUDED.responses,
         in_text = u.in_text + EXCLUDED.in_text,
         in_audio = u.in_audio + EXCLUDED.in_audio,
         in_image = u.in_image + EXCLUDED.in_image,
         cached_text = u.cached_text + EXCLUDED.cached_text,
         cached_audio = u.cached_audio + EXCLUDED.cached_audio,
         out_text = u.out_text + EXCLUDED.out_text,
         out_audio = u.out_audio + EXCLUDED.out_audio,
         cost_usd = u.cost_usd + EXCLUDED.cost_usd`,
      [
        deviceId,
        item.day,
        text(item.model, 60) || 'unknown',
        count(item.inText),
        count(item.inAudio),
        count(item.inImage),
        count(item.cachedText),
        count(item.cachedAudio),
        count(item.outText),
        count(item.outAudio),
        costOf(item, prices),
        count(item.responses),
      ],
    );
  }
  return true;
}

/** Should this workstation refuse new calls? Its own limit first, then the shared ones. */
export async function limitFor(
  device: Pick<DeviceRow, 'id' | 'monthly_limit_usd'>,
  settings: PortalSettings,
  now = Date.now(),
) {
  const db = await getDb();
  const month = monthOf(now);
  const [row] = await db.query<{ device: number | null; fleet: number | null }>(
    `SELECT SUM(cost_usd) FILTER (WHERE device_id = $1) AS device, SUM(cost_usd) AS fleet
     FROM usage_daily WHERE day LIKE $2`,
    [device.id, `${month}-%`],
  );
  const deviceLimit = device.monthly_limit_usd ?? settings.deviceMonthlyUsd;
  const overDevice = deviceLimit !== null && Number(row?.device ?? 0) >= deviceLimit;
  const overFleet = settings.monthlyBudgetUsd !== null && Number(row?.fleet ?? 0) >= settings.monthlyBudgetUsd;
  return { reached: overDevice || overFleet, enforced: (overDevice || overFleet) && settings.atLimit === 'block' };
}

export async function heartbeat(token: string, report: HeartbeatReport, now = Date.now()) {
  const db = await getDb();
  const [device] = await db.query<DeviceRow>(`SELECT * FROM devices WHERE token_hash = $1`, [hashToken(token)]);
  if (!device) return null;
  const settings = await getSettings();
  const inCall = report.inCall === true;
  await db.query(
    `UPDATE devices SET
       last_seen = $2, hostname = COALESCE(NULLIF($3, ''), hostname), windows_user = COALESCE(NULLIF($4, ''), windows_user),
       agent_name = COALESCE(NULLIF($5, ''), agent_name), version = COALESCE(NULLIF($6, ''), version),
       part_gatekeeper = $7, part_agent = $8, part_web = $9, in_call = $10,
       uptime_seconds = $11, memory_free_mb = $12, memory_total_mb = $13, disk_free_gb = $14
     WHERE id = $1`,
    [
      device.id,
      now,
      text(report.hostname),
      text(report.windowsUser),
      text(report.agentName),
      text(report.version),
      report.parts?.gatekeeper === true,
      report.parts?.agent === true,
      report.parts?.web === true,
      inCall,
      numberOrNull(report.uptimeSeconds),
      numberOrNull(report.memoryFreeMb),
      numberOrNull(report.memoryTotalMb),
      numberOrNull(report.diskFreeGb),
    ],
  );
  if (await recordUsage(device.id, report.usage, settings.prices, now)) await checkSpendAlerts(now);
  for (const result of report.results ?? []) await applyResult(device.id, result, now);
  await sweepCommands(now);

  const limit = await limitFor(device, settings, now);
  return {
    intervalSeconds: settings.heartbeatSeconds,
    active: device.active,
    limitReached: limit.enforced,
    // Never cut off a call: orders wait until it ends
    command: device.active && !inCall ? await claimCommand(device.id, now) : null,
  };
}

async function applyResult(deviceId: string, result: NonNullable<HeartbeatReport['results']>[number], now: number) {
  if (!['running', 'done', 'failed'].includes(result.status)) return;
  const db = await getDb();
  const rows = await db.query<CommandRow>(
    `UPDATE commands SET status = $3, detail = $4, updated_at = $5
     WHERE id = $1 AND device_id = $2 AND status IN ('sent', 'running') RETURNING *`,
    [text(result.id, 80), deviceId, result.status, text(result.detail, 500), now],
  );
  if (rows.length && result.status !== 'running') {
    const name = rows[0].type === 'update' ? 'Update' : 'Restart';
    const outcome = result.status === 'done' ? 'finished' : 'failed';
    await logActivity('system', `${name} ${outcome}`, deviceId, text(result.detail, 500), now);
  }
}

async function sweepCommands(now: number) {
  const db = await getDb();
  await db.query(`UPDATE commands SET status = 'expired', updated_at = $1 WHERE status = 'pending' AND expires_at < $1`, [
    now,
  ]);
  await db.query(
    `UPDATE commands SET status = 'failed', detail = 'No answer from the workstation', updated_at = $1
     WHERE status IN ('sent', 'running') AND updated_at < $2`,
    [now, now - STUCK_AFTER],
  );
}

async function claimCommand(deviceId: string, now: number) {
  const db = await getDb();
  // One at a time: nothing new while another is being carried out
  const busy = await db.query(`SELECT 1 FROM commands WHERE device_id = $1 AND status IN ('sent', 'running')`, [
    deviceId,
  ]);
  if (busy.length) return null;
  const [command] = await db.query<CommandRow>(
    `UPDATE commands SET status = 'sent', updated_at = $2 WHERE id = (
       SELECT id FROM commands WHERE device_id = $1 AND status = 'pending' ORDER BY created_at LIMIT 1
     ) AND status = 'pending' RETURNING *`,
    [deviceId, now],
  );
  if (!command) return null;
  if (command.type === 'restart') return { id: command.id, type: command.type };
  const [release] = await db.query<ReleaseRow>(`SELECT * FROM releases WHERE id = $1`, [command.release_id]);
  if (!release) {
    await db.query(`UPDATE commands SET status = 'failed', detail = 'That release was removed', updated_at = $2 WHERE id = $1`, [
      command.id,
      now,
    ]);
    return null;
  }
  return {
    id: command.id,
    type: command.type,
    version: release.version,
    url: release.url,
    sha256: release.sha256,
    signature: release.signature,
  };
}

// --- What the admin does --------------------------------------------------------------

export class FleetError extends Error {}

export async function latestRelease(): Promise<ReleaseRow | null> {
  const db = await getDb();
  const [release] = await db.query<ReleaseRow>(`SELECT * FROM releases ORDER BY published_at DESC LIMIT 1`);
  return release ?? null;
}

/** Queue an order for each workstation. Replaces any of the same kind still waiting. */
export async function queueCommand(
  deviceIds: string[],
  type: CommandType,
  actor: string,
  releaseId: string | null = null,
  now = Date.now(),
) {
  const db = await getDb();
  let release: ReleaseRow | null = null;
  if (type === 'update') {
    [release] = releaseId
      ? await db.query<ReleaseRow>(`SELECT * FROM releases WHERE id = $1`, [releaseId])
      : [await latestRelease()];
    if (!release) throw new FleetError('There is no release to install yet.');
  }
  let queued = 0;
  for (const deviceId of deviceIds) {
    const [device] = await db.query<DeviceRow>(`SELECT * FROM devices WHERE id = $1`, [deviceId]);
    if (!device?.active) continue;
    if (release && device.version === release.version) continue;
    await db.query(
      `UPDATE commands SET status = 'cancelled', detail = 'Replaced by a newer order', updated_at = $3
       WHERE device_id = $1 AND type = $2 AND status = 'pending'`,
      [deviceId, type, now],
    );
    await db.query(
      `INSERT INTO commands (id, device_id, type, release_id, status, created_by, created_at, updated_at, expires_at)
       VALUES ($1, $2, $3, $4, 'pending', $5, $6, $6, $7)`,
      [randomUUID(), deviceId, type, release?.id ?? null, actor, now, now + COMMAND_LIFETIME[type]],
    );
    const action = type === 'update' ? 'Asked to update' : 'Asked to restart';
    await logActivity(actor, action, deviceId, release?.version ?? '', now);
    queued++;
  }
  return { queued, version: release?.version ?? null };
}

export async function cancelCommand(commandId: string, actor: string, now = Date.now()) {
  const db = await getDb();
  const rows = await db.query<CommandRow>(
    `UPDATE commands SET status = 'cancelled', detail = 'Cancelled by the admin', updated_at = $2
     WHERE id = $1 AND status = 'pending' RETURNING *`,
    [commandId, now],
  );
  if (rows.length) await logActivity(actor, 'Cancelled an order', rows[0].device_id, rows[0].type, now);
  return rows.length > 0;
}

export async function setActive(deviceId: string, active: boolean, actor: string, now = Date.now()) {
  const db = await getDb();
  const rows = await db.query(`UPDATE devices SET active = $2 WHERE id = $1 RETURNING id`, [deviceId, active]);
  if (!rows.length) return false;
  if (!active) {
    await db.query(
      `UPDATE commands SET status = 'cancelled', detail = 'The workstation was deactivated', updated_at = $2
       WHERE device_id = $1 AND status = 'pending'`,
      [deviceId, now],
    );
  }
  await logActivity(actor, active ? 'Activated' : 'Deactivated', deviceId, '', now);
  return true;
}

export async function updateDevice(
  deviceId: string,
  changes: { label?: unknown; monthlyLimitUsd?: unknown },
  actor: string,
  now = Date.now(),
) {
  const db = await getDb();
  if (changes.label !== undefined) {
    await db.query(`UPDATE devices SET label = $2 WHERE id = $1`, [deviceId, text(changes.label, 80).trim()]);
  }
  if (changes.monthlyLimitUsd !== undefined) {
    const value = changes.monthlyLimitUsd;
    if (value !== null && !(typeof value === 'number' && value > 0)) {
      throw new FleetError('Enter an amount above 0, or leave it empty.');
    }
    await db.query(`UPDATE devices SET monthly_limit_usd = $2 WHERE id = $1`, [deviceId, value]);
    const detail = value === null ? 'Uses the shared limit' : `$${value}`;
    await logActivity(actor, 'Changed the limit', deviceId, detail, now);
  }
}

/** A retired workstation: its key stops working, and it would have to join again. */
export async function removeDevice(deviceId: string, actor: string, now = Date.now()) {
  const db = await getDb();
  const [device] = await db.query<DeviceRow>(`DELETE FROM devices WHERE id = $1 RETURNING *`, [deviceId]);
  if (device) await logActivity(actor, 'Removed a workstation', null, device.label || device.hostname, now);
  return Boolean(device);
}

export async function addRelease(
  body: { version?: unknown; url?: unknown; sha256?: unknown; signature?: unknown; notes?: unknown; sizeBytes?: unknown },
  actor: string,
  now = Date.now(),
) {
  const version = text(body.version, 60).trim();
  const url = text(body.url, 1000).trim();
  const sha256 = text(body.sha256, 64).toLowerCase();
  const signature = text(body.signature, 2000).trim();
  if (!version) throw new FleetError('A release needs a version.');
  if (!/^https?:\/\//.test(url)) throw new FleetError('A release needs a download address.');
  if (!/^[a-f0-9]{64}$/.test(sha256)) throw new FleetError('A release needs its SHA-256.');
  if (!signature) throw new FleetError('A release needs its signature.');
  const db = await getDb();
  const added = await db.query<ReleaseRow>(
    `INSERT INTO releases (id, version, url, sha256, signature, notes, size_bytes, published_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8) ON CONFLICT (version) DO NOTHING RETURNING *`,
    [randomUUID(), version, url, sha256, signature, text(body.notes, 2000), count(body.sizeBytes), now],
  );
  if (!added.length) throw new FleetError(`Version ${version} was already published.`);
  await logActivity(actor, 'Published a release', null, version, now);
  return added[0];
}

// --- What the portal shows ---------------------------------------------------------------

export interface DeviceView {
  id: string;
  name: string;
  label: string;
  hostname: string;
  windowsUser: string;
  license: string;
  version: string;
  state: DeviceState;
  online: boolean;
  active: boolean;
  inCall: boolean;
  lastSeen: number;
  enrolledAt: number;
  parts: { gatekeeper: boolean; agent: boolean; web: boolean };
  uptimeSeconds: number | null;
  memoryFreeMb: number | null;
  memoryTotalMb: number | null;
  diskFreeGb: number | null;
  monthlyLimitUsd: number | null;
  limitUsd: number | null;
  monthCostUsd: number;
  order: { id: string; type: CommandType; status: CommandStatus; detail: string; version: string | null } | null;
}

export async function listDevices(now = Date.now()): Promise<DeviceView[]> {
  const db = await getDb();
  const settings = await getSettings();
  const devices = await db.query<DeviceRow>(
    `SELECT * FROM devices ORDER BY COALESCE(NULLIF(label, ''), hostname), enrolled_at`,
  );
  const costs = await db.query<{ device_id: string; cost: number }>(
    `SELECT device_id, SUM(cost_usd) AS cost FROM usage_daily WHERE day LIKE $1 GROUP BY device_id`,
    [`${monthOf(now)}-%`],
  );
  const orders = await db.query<CommandRow & { version: string | null }>(
    `SELECT c.*, r.version FROM commands c LEFT JOIN releases r ON r.id = c.release_id
     WHERE c.status IN ('pending', 'sent', 'running') ORDER BY c.status <> 'pending', c.created_at`,
  );
  const cost = new Map(costs.map((row) => [row.device_id, Number(row.cost)]));
  // What is being carried out, before what is waiting (last one wins)
  const order = new Map(orders.map((row) => [row.device_id, row]));
  return devices.map((device) => {
    const current = order.get(device.id);
    const updating = current?.type === 'update' && current.status !== 'pending';
    return {
      id: device.id,
      name: device.label || device.hostname || 'Unnamed PC',
      label: device.label,
      hostname: device.hostname,
      windowsUser: device.windows_user,
      license: device.license,
      version: device.version,
      state: deviceState(device, settings, updating, now),
      online: now - device.last_seen <= settings.offlineAfterSeconds * 1000,
      active: device.active,
      inCall: device.in_call,
      lastSeen: device.last_seen,
      enrolledAt: device.enrolled_at,
      parts: { gatekeeper: device.part_gatekeeper, agent: device.part_agent, web: device.part_web },
      uptimeSeconds: device.uptime_seconds,
      memoryFreeMb: device.memory_free_mb,
      memoryTotalMb: device.memory_total_mb,
      diskFreeGb: device.disk_free_gb,
      monthlyLimitUsd: device.monthly_limit_usd,
      limitUsd: device.monthly_limit_usd ?? settings.deviceMonthlyUsd,
      monthCostUsd: cost.get(device.id) ?? 0,
      order: current
        ? { id: current.id, type: current.type, status: current.status, detail: current.detail, version: current.version }
        : null,
    };
  });
}

export async function deviceHistory(deviceId: string) {
  const db = await getDb();
  return db.query<CommandRow & { version: string | null }>(
    `SELECT c.*, r.version FROM commands c LEFT JOIN releases r ON r.id = c.release_id
     WHERE c.device_id = $1 ORDER BY c.created_at DESC LIMIT 20`,
    [deviceId],
  );
}

function lastDays(days: number, now: number): string[] {
  return Array.from({ length: days }, (_, i) =>
    new Date(now - (days - 1 - i) * 24 * HOUR).toISOString().slice(0, 10),
  );
}

export async function dailyCost(deviceId: string | null, now = Date.now(), days = 30) {
  const db = await getDb();
  const range = lastDays(days, now);
  const rows = await db.query<{ day: string; cost: number }>(
    `SELECT day, SUM(cost_usd) AS cost FROM usage_daily
     WHERE day >= $1 AND ($2::text IS NULL OR device_id = $2) GROUP BY day`,
    [range[0], deviceId],
  );
  const cost = new Map(rows.map((row) => [row.day, Number(row.cost)]));
  return range.map((day) => ({ day, cost: cost.get(day) ?? 0 }));
}

/** One page of days for the history charts; page 0 ends today. */
export async function usageHistory(days: number, page: number, now = Date.now()) {
  const db = await getDb();
  const end = now - page * days * 24 * HOUR;
  const range = lastDays(days, end);
  const rows = await db.query<{ day: string; name: string; model: string; cost: number; responses: number }>(
    `SELECT u.day, COALESCE(NULLIF(d.label, ''), d.hostname) AS name, u.model, u.cost_usd AS cost, u.responses
     FROM usage_daily u JOIN devices d ON d.id = u.device_id WHERE u.day >= $1 AND u.day <= $2`,
    [range[0], range[range.length - 1]],
  );
  const [first] = await db.query<{ day: string | null }>(`SELECT MIN(day) AS day FROM usage_daily`);
  return {
    days: range,
    hasEarlier: Boolean(first?.day && first.day < range[0]),
    rows: rows.map((row) => ({
      day: row.day,
      name: row.name || 'Unnamed PC',
      model: row.model,
      cost: Number(row.cost),
      responses: Number(row.responses),
    })),
  };
}

/** Spend per month and per week (Monday to Sunday, UTC), each with its workstations. */
export async function spendPeriods(now = Date.now(), months = 6, weeks = 12) {
  const db = await getDb();
  const settings = await getSettings();
  const date = new Date(now);
  const from = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() - (months - 1), 1)).toISOString().slice(0, 10);
  const rows = await db.query<{ day: string; name: string; cost: number }>(
    `SELECT u.day, COALESCE(NULLIF(d.label, ''), d.hostname) AS name, SUM(u.cost_usd) AS cost
     FROM usage_daily u JOIN devices d ON d.id = u.device_id WHERE u.day >= $1 GROUP BY u.day, d.label, d.hostname`,
    [from],
  );
  const short = (at: Date) => at.toLocaleDateString('en-SG', { day: 'numeric', month: 'short', timeZone: 'UTC' });
  const period = (label: string, start: string, end: string, budget: number | null) => {
    const breakdown = new Map<string, number>();
    for (const row of rows) {
      if (row.day >= start && row.day <= end) {
        breakdown.set(row.name || 'Unnamed PC', (breakdown.get(row.name || 'Unnamed PC') ?? 0) + Number(row.cost));
      }
    }
    const cost = [...breakdown.values()].reduce((sum, value) => sum + value, 0);
    return {
      label,
      cost,
      percentOfBudget: budget ? (cost / budget) * 100 : null,
      breakdown: [...breakdown.entries()].map(([name, value]) => ({ name, cost: value })).sort((a, b) => b.cost - a.cost),
    };
  };
  const monthRows = Array.from({ length: months }, (_, back) => {
    const start = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() - back, 1));
    const end = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() - back + 1, 0));
    const label = start.toLocaleDateString('en-SG', { month: 'long', year: 'numeric', timeZone: 'UTC' });
    return period(label, start.toISOString().slice(0, 10), end.toISOString().slice(0, 10), settings.monthlyBudgetUsd);
  });
  const monday = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()) - ((date.getUTCDay() + 6) % 7) * 24 * HOUR;
  const weekRows = Array.from({ length: weeks }, (_, back) => {
    const start = new Date(monday - back * 7 * 24 * HOUR);
    const end = new Date(start.getTime() + 6 * 24 * HOUR);
    return period(`${short(start)} – ${short(end)}`, start.toISOString().slice(0, 10), end.toISOString().slice(0, 10), null);
  });
  return {
    months: monthRows.filter((row, index) => index === 0 || row.cost > 0),
    weeks: weekRows.filter((row, index) => index === 0 || row.cost > 0),
  };
}

export async function usageSummary(now = Date.now()) {
  const db = await getDb();
  const settings = await getSettings();
  const month = monthOf(now);
  const [totals] = await db.query<Record<string, number | null>>(
    `SELECT SUM(cost_usd) AS cost, SUM(in_text) AS in_text, SUM(in_audio) AS in_audio, SUM(in_image) AS in_image,
       SUM(cached_text) + SUM(cached_audio) AS cached, SUM(out_text) AS out_text, SUM(out_audio) AS out_audio
     FROM usage_daily WHERE day LIKE $1`,
    [`${month}-%`],
  );
  const models = await db.query<{ model: string; cost: number }>(
    `SELECT model, SUM(cost_usd) AS cost FROM usage_daily WHERE day LIKE $1 GROUP BY model ORDER BY cost DESC`,
    [`${month}-%`],
  );
  const monthCost = Number(totals?.cost ?? 0);
  const date = new Date(now);
  const daysInMonth = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).getUTCDate();
  const num = (key: string) => Number(totals?.[key] ?? 0);
  return {
    month,
    monthCostUsd: monthCost,
    // A straight line from this month so far
    onPaceUsd: (monthCost / date.getUTCDate()) * daysInMonth,
    budgetUsd: settings.monthlyBudgetUsd,
    warnPercent: settings.warnPercent,
    atLimit: settings.atLimit,
    tokens: {
      inText: num('in_text'),
      inAudio: num('in_audio'),
      inImage: num('in_image'),
      cached: num('cached'),
      outText: num('out_text'),
      outAudio: num('out_audio'),
    },
    models: models.map((row) => ({ model: row.model, cost: Number(row.cost) })),
    daily: await dailyCost(null, now),
  };
}

export async function listReleases() {
  const db = await getDb();
  const releases = await db.query<ReleaseRow>(`SELECT * FROM releases ORDER BY published_at DESC LIMIT 50`);
  const installed = await db.query<{ version: string; n: number }>(
    `SELECT version, COUNT(*) AS n FROM devices GROUP BY version`,
  );
  const on = new Map(installed.map((row) => [row.version, Number(row.n)]));
  return releases.map((release, index) => ({
    id: release.id,
    version: release.version,
    url: release.url,
    notes: release.notes,
    sizeBytes: release.size_bytes,
    publishedAt: release.published_at,
    isLatest: index === 0,
    installedOn: on.get(release.version) ?? 0,
  }));
}

export async function listActivity(limit = 100) {
  const db = await getDb();
  return db.query<{
    id: string;
    at: number;
    actor: string;
    action: string;
    device_id: string | null;
    detail: string;
    device: string | null;
  }>(
    `SELECT a.*, COALESCE(NULLIF(d.label, ''), d.hostname) AS device
     FROM activity a LEFT JOIN devices d ON d.id = a.device_id ORDER BY a.at DESC LIMIT $1`,
    [limit],
  );
}
