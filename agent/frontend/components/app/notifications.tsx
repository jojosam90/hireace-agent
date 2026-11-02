'use client';

import { useEffect } from 'react';
import { toast } from 'sonner';
import { useSessionContext } from '@livekit/components-react';
import { useUiLanguage } from '@/lib/i18n';
import { openInBrowser } from '@/lib/open-link';

// Must match NOTIFY_TOPIC in the agent's src/office_tools.py
const NOTIFY_TOPIC = 'hireace.notify';

interface EmailSent {
  type: 'email_sent';
  to: string[];
  subject: string;
  attachments: string[];
  gmail_link: string;
}

/** Notices the agent sends during a call, e.g. "Email sent" with an Open in Gmail button. */
export function Notifications() {
  const { room } = useSessionContext();
  const { t } = useUiLanguage();

  useEffect(() => {
    if (!room) return;
    room.registerTextStreamHandler(NOTIFY_TOPIC, async (reader) => {
      const event = JSON.parse(await reader.readAll()) as EmailSent;
      if (event.type !== 'email_sent') return;
      const attached = event.attachments.length ? ` · ${event.attachments.join(', ')}` : '';
      toast.success(t('emailSent', { to: event.to.join(', ') }), {
        description: `${event.subject}${attached}`,
        duration: 30000,
        action: { label: t('openGmail'), onClick: () => openInBrowser(event.gmail_link) },
      });
    });
    return () => room.unregisterTextStreamHandler(NOTIFY_TOPIC);
  }, [room, t]);

  return null;
}
