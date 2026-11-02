'use client';

import { useEffect, useState } from 'react';
import { ArrowsOutIcon, DeviceMobileIcon } from '@phosphor-icons/react/dist/ssr';
import { Button } from '@/components/ui/button';
import { useUiLanguage } from '@/lib/i18n';

// Must match the panel window start.ps1 opens
const MOBILE_WIDTH = 380;
const MOBILE_HEIGHT = 860;
const MOBILE_MARGIN = 20;

function isFullView() {
  return window.outerWidth > MOBILE_WIDTH * 1.5 || document.fullscreenElement !== null;
}

/**
 * Switches the HireAce panel between full view (the whole screen) and mobile view
 * (the narrow vertical panel in the top-right corner). The panel is a Chrome app
 * window, which may resize itself; in a normal browser tab that is not allowed,
 * so full view falls back to browser full screen. Hidden on phones and tablets.
 */
export function ViewModeToggle() {
  const { t } = useUiLanguage();
  const [full, setFull] = useState(false);

  useEffect(() => {
    const update = () => setFull(isFullView());
    update();
    window.addEventListener('resize', update);
    document.addEventListener('fullscreenchange', update);
    return () => {
      window.removeEventListener('resize', update);
      document.removeEventListener('fullscreenchange', update);
    };
  }, []);

  const showFull = () => {
    const { availLeft, availTop, availWidth, availHeight } = screen as Screen & {
      availLeft: number;
      availTop: number;
    };
    const before = window.outerWidth;
    window.moveTo(availLeft, availTop);
    window.resizeTo(availWidth, availHeight);
    // Ignored in a normal browser tab: use full screen there instead
    setTimeout(() => {
      if (window.outerWidth === before) {
        document.documentElement.requestFullscreen().catch(() => {});
      }
    }, 300);
  };

  const showMobile = () => {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
      return;
    }
    const { availLeft, availTop, availWidth, availHeight } = screen as Screen & {
      availLeft: number;
      availTop: number;
    };
    window.resizeTo(MOBILE_WIDTH, Math.min(MOBILE_HEIGHT, availHeight - 2 * MOBILE_MARGIN));
    window.moveTo(availLeft + availWidth - MOBILE_WIDTH - MOBILE_MARGIN, availTop + MOBILE_MARGIN);
  };

  return (
    <Button
      variant="outline"
      size="sm"
      className="fixed top-4 left-14 z-50 md:left-40 pointer-coarse:hidden"
      title={full ? t('mobileView') : t('fullView')}
      onClick={full ? showMobile : showFull}
    >
      {full ? <DeviceMobileIcon /> : <ArrowsOutIcon />}
      {full ? t('mobileView') : t('fullView')}
    </Button>
  );
}
