/**
 * Opens a Gmail link (e.g. "Open in Gmail" after an email was sent) in HireAce's
 * browser on the PC, where Gmail is signed in; from a phone, or if that fails, in a
 * new tab.
 */
export async function openInBrowser(url: string) {
  // Opened from a phone or another device: open it there, straight away (phones
  // block new tabs opened after a wait)
  if (!['localhost', '127.0.0.1'].includes(window.location.hostname)) {
    window.open(url, '_blank', 'noopener');
    return;
  }
  try {
    const res = await fetch('/api/gmail/open', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ link: url }),
    });
    if (res.ok && !(await res.json()).reason) return;
  } catch {
    // fall through
  }
  window.open(url, '_blank', 'noopener');
}
