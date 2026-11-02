'use client';

import { useEffect, useState } from 'react';
import type { Room } from 'livekit-client';
import { useSessionContext } from '@livekit/components-react';
import { Button } from '@/components/ui/button';
import { useUiLanguage } from '@/lib/i18n';

// Must match the agent's src/approval_rpc.py
const APPROVALS_METHOD = 'hireace.approvals';
const DECIDE_METHOD = 'hireace.decide';

interface PendingApproval {
  id: string;
  action: string;
  args: Record<string, string>;
  summary: string;
  reason: string;
}

/**
 * Asks the agent in the call, so it works wherever this app runs (e.g. on Vercel,
 * opened on a phone). Outside a call: the gatekeeper on this PC, if there is one.
 */
async function callAgent(room: Room | undefined, method: string, payload = '') {
  const agent = room && [...room.remoteParticipants.values()].find((p) => p.isAgent);
  if (!agent) return null;
  return room.localParticipant.performRpc({
    destinationIdentity: agent.identity,
    method,
    payload,
  });
}

/**
 * Shows actions HireAce is waiting to run. Approving here is equivalent to saying
 * "yes" out loud; payments never appear because the gatekeeper denies them outright.
 */
export function ApprovalPanel() {
  const { t } = useUiLanguage();
  const { room } = useSessionContext();
  const [pending, setPending] = useState<PendingApproval[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  // Worded in the UI language from the action itself, not the gatekeeper's English summary
  const describe = (item: PendingApproval) => {
    const args = item.args ?? {};
    switch (item.action) {
      case 'click':
        return t('actionClick', { target: args.target ?? '' });
      case 'type_text':
        return t('actionType', { target: args.target ?? '' });
      case 'open_url':
        return t('actionOpen', { url: args.url ?? '' });
      case 'press_key':
        return t('actionKey', { key: args.key ?? '' });
      case 'screen_click':
      case 'screen_drag':
        return t('actionScreenClick');
      case 'screen_type':
        return t('actionScreenType');
      case 'screen_key':
        return t('actionScreenKey', { keys: args.keys ?? '' });
      case 'close_window':
        return t('actionCloseWindow', { title: args.title ?? '' });
      case 'open_file':
        return t('actionOpenFile', { name: (args.path ?? '').split(/[\\/]/).pop() ?? '' });
      case 'send_email':
        return t('actionSendEmail', { subject: args.subject ?? '' });
      case 'send_quotation':
        return t('actionSendQuotation', { to: args.to ?? '' });
      case 'save_quotation':
        return t('actionSaveQuotation', { quote: args.quote_number ?? '' });
      default:
        return item.summary;
    }
  };

  const reason = (item: PendingApproval) => {
    if (item.action === 'send_email') return t('reasonSendEmail');
    if (item.action === 'send_quotation') return t('reasonSendQuotation');
    if (item.action === 'save_quotation') return t('reasonSaveQuotation');
    if (item.action === 'close_window') return t('reasonCloseWindow');
    if (item.action === 'open_file') return t('reasonMacros');
    if (item.reason.includes('outside the browser')) return t('reasonOutsideBrowser');
    if (item.reason.includes('password')) return t('reasonPassword');
    return t('reasonConsequential');
  };

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const fromAgent = await callAgent(room, APPROVALS_METHOD);
        if (fromAgent !== null) {
          if (active) setPending(JSON.parse(fromAgent));
          return;
        }
        // Only the PC itself runs a gatekeeper (not the shared site on a phone)
        if (!['localhost', '127.0.0.1'].includes(window.location.hostname)) {
          if (active) setPending([]);
          return;
        }
        const res = await fetch('/api/approvals', { cache: 'no-store' });
        if (active && res.ok) setPending(await res.json());
      } catch {
        // agent busy or gatekeeper not running: try again on the next tick
      }
    };
    poll();
    const timer = setInterval(poll, 1500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [room]);

  const decide = async (id: string, decision: 'approve' | 'deny') => {
    setBusy(id);
    try {
      const payload = JSON.stringify({ id, decision });
      if ((await callAgent(room, DECIDE_METHOD, payload)) === null) {
        await fetch(`/api/approvals/${id}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision }),
        });
      }
      setPending((items) => items.filter((item) => item.id !== id));
    } finally {
      setBusy(null);
    }
  };

  if (pending.length === 0) return null;

  return (
    <div className="fixed top-4 left-1/2 z-50 flex w-[min(92vw,28rem)] -translate-x-1/2 flex-col gap-2">
      {pending.map((item) => (
        <div
          key={item.id}
          role="alertdialog"
          aria-label={t('approvalLabel')}
          className="bg-background rounded-xl border p-4 shadow-lg"
        >
          <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            {t('approvalHeading')}
          </p>
          <p className="mt-1 font-medium">{describe(item)}</p>
          <p className="text-muted-foreground mt-1 text-sm">{reason(item)}</p>
          <p className="text-muted-foreground mt-1 text-xs">
            {item.action === 'send_quotation'
              ? t('approvalThisEmailOnly')
              : item.action === 'save_quotation'
                ? t('approvalThisQuotationOnly')
                : t('approvalCoversCall')}
          </p>
          <div className="mt-3 flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={busy === item.id}
              onClick={() => decide(item.id, 'deny')}
            >
              {t('deny')}
            </Button>
            <Button
              size="sm"
              disabled={busy === item.id}
              onClick={() => decide(item.id, 'approve')}
            >
              {t('approve')}
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}
