import type { CommandRow, DeviceView } from './fleet';
import type { PortalSettings } from './settings';

export type { DeviceView, PortalSettings };

export interface DevicesData {
  devices: DeviceView[];
  latestVersion: string | null;
  heartbeatSeconds: number;
  offlineAfterSeconds: number;
}

export interface DeviceData {
  device: DeviceView;
  history: (CommandRow & { version: string | null })[];
  daily: { day: string; cost: number }[];
  latestVersion: string | null;
}

export interface UsageData {
  month: string;
  monthCostUsd: number;
  onPaceUsd: number;
  budgetUsd: number | null;
  warnPercent: number;
  atLimit: 'warn' | 'block';
  tokens: Record<'inText' | 'inAudio' | 'inImage' | 'cached' | 'outText' | 'outAudio', number>;
  models: { model: string; cost: number }[];
  daily: { day: string; cost: number }[];
  billed: { usd: number; at: number } | null;
  adminKeySet: boolean;
  devices: { id: string; name: string; cost: number; limit: number | null }[];
}

export interface ReleaseView {
  id: string;
  version: string;
  url: string;
  notes: string;
  sizeBytes: number;
  publishedAt: number;
  isLatest: boolean;
  installedOn: number;
}

export interface ActivityRow {
  id: string;
  at: number;
  actor: string;
  action: string;
  device_id: string | null;
  detail: string;
  device: string | null;
}
