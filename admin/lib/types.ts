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

export interface PeriodRow {
  label: string;
  cost: number;
  percentOfBudget: number | null;
  breakdown: { name: string; cost: number }[];
}

export interface UsageHistoryData {
  days: string[];
  hasEarlier: boolean;
  rows: { day: string; name: string; model: string; cost: number; responses: number }[];
  months: PeriodRow[];
  weeks: PeriodRow[];
}

export interface AlertView {
  id: string;
  severity: 'warn' | 'critical';
  title: string;
  detail: string;
  device_id: string | null;
  created_at: number;
  acknowledged_by: string | null;
  emailed_at: number | null;
  email_error: string;
}

export interface AlertsData {
  open: AlertView[];
  past: AlertView[];
  emailReady: boolean;
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
