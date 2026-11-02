"""Gmail in HireAce's own Chrome window, on standby.

The user opens Gmail there once (Settings > Open Gmail) and signs in; the window
keeps its own profile, so it stays signed in. No Google Cloud project or API keys.
Only the gatekeeper uses this.

Sending fills in Gmail's own compose page in a new tab of that window, attaches the
files through the page (no mouse, no file dialog), sends with Ctrl+Enter and closes
the tab, so the user's Gmail tab stays as it was. Everything that depends on Gmail's
page is here, kept to markers that have been stable for years and do not depend on
the language of Gmail: the compose body (g_editable), the file input and Ctrl+Enter.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from browser import BrowserManager
from local_desktop import browser_tabs

GMAIL_URL = "https://mail.google.com/"
SEND_TIMEOUT_S = 60

NOT_READY = (
    "Gmail is not open and signed in in HireAce's browser. Ask the user to open "
    "Settings (the gear icon), tap Open Gmail and sign in there, then try again."
)

logger = logging.getLogger("hireace.gmail")

_ACCOUNT = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_ACCOUNT_PATH = re.compile(r"/mail/u/\d+/")
# Gmail, and Google's account chooser that leads to it
_GOOGLE_HOSTS = {"mail.google.com", "accounts.google.com"}


# A signed-in Gmail tab names its account: "Inbox (3) - name@gmail.com - Gmail" (or
# "- Company Mail" on Workspace), so a search page about Gmail does not count
_SIGNED_IN_TAB = re.compile(
    r"-\s*([\w.+-]+@[\w-]+(?:\.[\w-]+)+)\s*-\s*[^-]*mail\b", re.IGNORECASE
)
_BROWSER_NAMES = {
    "chrome": "Chrome",
    "msedge": "Edge",
    "firefox": "Firefox",
    "brave": "Brave",
    "opera": "Opera",
}
HEALTH_CACHE_S = 15  # reading every browser's tabs takes about a second of CPU


class GmailError(Exception):
    """A user-facing Gmail failure."""


def signed_in_accounts(windows: list[dict]) -> list[dict]:
    """The Gmail accounts open in these browser windows, without repeats."""
    found: list[dict] = []
    for window in windows:
        for tab in window.get("tabs") or []:
            match = _SIGNED_IN_TAB.search(tab)
            if not match:
                continue
            browser = window.get("browser", "")
            account = {
                "browser": _BROWSER_NAMES.get(browser, browser),
                "email": match.group(1).lower(),
            }
            if account not in found:
                found.append(account)
    return found


class GmailWindow:
    def __init__(self, browser: BrowserManager) -> None:
        self._browser = browser
        self._health: tuple[float, dict] | None = None
        self._health_lock = asyncio.Lock()

    async def health(self) -> dict:
        """Is Gmail signed in anywhere: every open browser, read-only (no tab is
        switched). can_send: signed in in HireAce's own browser, where sending works."""
        async with self._health_lock:
            if self._health and time.monotonic() - self._health[0] < HEALTH_CACHE_S:
                return self._health[1]
            checked = True
            try:
                tabs = await asyncio.to_thread(browser_tabs)
                accounts = signed_in_accounts(tabs["windows"])
            except Exception as exc:
                logger.warning("could not read the browser tabs: %s", exc)
                checked, accounts = False, []
            own = await self.status()
            result = {
                "checked": checked,
                "connected": bool(accounts) or own["state"] == "ready",
                "accounts": accounts,
                "can_send": own["state"] == "ready",
            }
            self._health = (time.monotonic(), result)
            return result

    async def status(self) -> dict:
        """ "ready" (signed in, can send), "signed_out", "not_open" or "closed"
        (HireAce's browser is not running). Never opens anything."""
        if not self._browser.running:
            return {"state": "closed", "email": ""}
        tab = self._tab()
        if tab is None:
            return {"state": "not_open", "email": ""}
        # Signed in, Gmail's title names the account: "Inbox (3) - name@gmail.com - Gmail"
        found = _ACCOUNT.search(await tab.title())
        if not found:
            return {"state": "signed_out", "email": ""}
        return {"state": "ready", "email": found.group(0).lower()}

    async def open(self, link: str = "") -> dict:
        """Show Gmail in HireAce's browser (its sign-in page if signed out), or one
        Gmail link there (e.g. an email just sent: "Open in Gmail")."""
        if link and urlparse(link).hostname not in _GOOGLE_HOSTS:
            raise GmailError("Only Gmail links can be opened.")
        await self._browser.open_url(link or GMAIL_URL)
        return await self.status()

    async def send(
        self, to: list[str], subject: str, text: str, attachments: list[str]
    ) -> dict:
        """Send a plain-text email from the signed-in account. Returns the sender."""
        status = await self.status()
        if status["state"] != "ready":
            raise GmailError(NOT_READY)
        account = _ACCOUNT_PATH.search(self._tab().url)
        query = urlencode(
            {"view": "cm", "fs": "1", "to": ",".join(to), "su": subject, "body": text}
        )
        path = account.group(0) if account else "/mail/"
        url = f"https://mail.google.com{path}?{query}"

        page = await self._browser.new_page()
        try:
            await page.bring_to_front()
            await page.goto(url, wait_until="domcontentloaded")
            body = page.locator('div[g_editable="true"]').first
            await body.wait_for(state="visible", timeout=30_000)
            if attachments:
                await self._attach(page, attachments)
            await body.click()
            await page.keyboard.press("Control+Enter")
            # Sent: Gmail closes the compose page
            await body.wait_for(state="detached", timeout=SEND_TIMEOUT_S * 1000)
        except PlaywrightTimeoutError as exc:
            raise GmailError(await _why_not_sent(page)) from exc
        finally:
            if not page.is_closed():
                await page.close()
        return {"from": status["email"]}

    def _tab(self) -> Page | None:
        for page in self._browser.pages():
            if page.url.startswith("https://mail.google.com/mail/"):
                return page
        return None

    @staticmethod
    async def _attach(page: Page, attachments: list[str]) -> None:
        await page.locator('input[type="file"]').first.set_input_files(attachments)
        # Each file shows in the compose page by name once added...
        for path in attachments:
            await page.get_by_text(Path(path).name).first.wait_for(timeout=30_000)
        # ...and is sent once its upload bar is gone
        deadline = time.monotonic() + SEND_TIMEOUT_S
        while await page.locator('[role="progressbar"]:visible').count():
            if time.monotonic() > deadline:
                raise PlaywrightTimeoutError("attachments still uploading")
            await asyncio.sleep(0.5)


async def _why_not_sent(page: Page) -> str:
    """Gmail's own message if it showed one (e.g. a bad address), else a general one."""
    try:
        dialog = page.locator('[role="alertdialog"]:visible').first
        if await dialog.count():
            message = " ".join((await dialog.inner_text()).split())
            return f"Gmail did not send it: {message}"
    except Exception:
        pass
    return (
        "Gmail did not finish sending in time. It may still be in Gmail's Outbox or "
        "Drafts: check there before sending again."
    )
