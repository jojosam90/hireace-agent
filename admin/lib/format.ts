export function usd(value: number): string {
  const digits = value !== 0 && Math.abs(value) < 10 ? 2 : value % 1 === 0 ? 0 : 2;
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

export function ago(at: number, now = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - at) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)} h ago`;
  return `${Math.floor(seconds / 86_400)} d ago`;
}

export function dateTime(at: number): string {
  return new Date(at).toLocaleString('en-SG', { dateStyle: 'medium', timeStyle: 'short' });
}

export function shortDay(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString('en-SG', { day: 'numeric', month: 'short', timeZone: 'UTC' });
}

export function compact(value: number): string {
  return value.toLocaleString('en-US', { notation: 'compact', maximumFractionDigits: 1 });
}

export function duration(seconds: number): string {
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3600);
  if (days) return `${days} d ${hours} h`;
  return hours ? `${hours} h ${Math.floor((seconds % 3600) / 60)} min` : `${Math.floor(seconds / 60)} min`;
}
