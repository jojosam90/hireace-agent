import type { ReactNode } from 'react';
import { Shell } from '@/components/shell';

export default function PortalLayout({ children }: { children: ReactNode }) {
  return <Shell>{children}</Shell>;
}
