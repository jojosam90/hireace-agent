// Which PC a phone controls. Every installation has its own agent name
// (start.ps1: hireace-<10 hex digits>), and its phone link carries it: ?pc=<name>.
// The phone remembers it in a cookie, so the plain site address works afterwards.

export const PC_COOKIE = 'hireace-pc';
const PC_NAME = /^hireace-[0-9a-f]{10}$/;

export function validPc(value: string | null | undefined): string | undefined {
  return value && PC_NAME.test(value) ? value : undefined;
}

export function phoneLink(siteUrl: string, agentName: string): string {
  return `${siteUrl.replace(/\/+$/, '')}/?pc=${agentName}`;
}
