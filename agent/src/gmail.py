"""The user's Gmail: already open and signed in in one of their browsers (Edge,
Chrome...), or in HireAce's own Chrome window. No Google Cloud project or API keys.
Only the gatekeeper uses this.

health() reads the tabs of every open browser, without switching any. Sending uses
the Gmail it finds: in HireAce's own window (Playwright: nothing on screen moves) if
it is signed in there, else in the user's browser (gmail_send.ps1). Both fill in
Gmail's own compose page in a new tab, send and close the tab, so the user's Gmail tab
stays as it was. Everything that depends on Gmail's page is here and in that script.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
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
    "Gmail is not open on this PC. Ask the user to open Gmail in Chrome or Edge and "
    "sign in, then try again."
)
# Longer and Gmail's compose address may be cut short
MAX_COMPOSE_URL = 8000
_SEND_SCRIPT = Path(__file__).with_name("gmail_send.ps1")

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
# Reading every browser's tabs takes about a second; the panel asks every 10 s
HEALTH_CACHE_S = 8


class GmailError(Exception):
    """A user-facing Gmail failure."""


def signed_in_accounts(windows: list[dict]) -> list[dict]:
    """The Gmail accounts open in these browser windows, without repeats: browser
    (its name), process (to start it) and email."""
    found: list[dict] = []
    for window in windows:
        # The window's title too: it names the active tab even when minimized
        for tab in [*(window.get("tabs") or []), window.get("title") or ""]:
            match = _SIGNED_IN_TAB.search(tab)
            if not match:
                continue
            browser = window.get("browser", "")
            account = {
                "browser": _BROWSER_NAMES.get(browser, browser),
                "process": browser,
                "email": match.group(1).lower(),
            }
            if account not in found:
                found.append(account)
    return found


def send_in_browser(job: dict) -> dict:
    """Runs gmail_send.ps1 (blocking, up to a few minutes with attachments)."""
    done = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_SEND_SCRIPT),
        ],
        input=json.dumps(job),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if done.returncode != 0 or not done.stdout.strip():
        return {
            "sent": False,
            "maybe_sent": True,
            "reason": f"Sending stopped unexpectedly: {done.stderr.strip()[:200]}",
        }
    return json.loads(done.stdout.strip().splitlines()[-1])


class GmailWindow:
    def __init__(self, browser: BrowserManager) -> None:
        self._browser = browser
        self._health: tuple[float, dict] | None = None
        self._health_lock = asyncio.Lock()
        self._known_tabs: dict[int, list[str]] = {}  # window -> its tabs when last seen

    async def health(self) -> dict:
        """Is Gmail signed in anywhere: every open browser, read-only (no tab is
        switched)."""
        async with self._health_lock:
            if self._health and time.monotonic() - self._health[0] < HEALTH_CACHE_S:
                return self._health[1]
            checked = True
            try:
                accounts = await self._open_accounts()
            except Exception as exc:
                logger.warning("could not read the browser tabs: %s", exc)
                checked, accounts = False, []
            own = await self.status()
            connected = bool(accounts) or own["state"] == "ready"
            result = {
                "checked": checked,
                "connected": connected,
                "accounts": [
                    {"browser": a["browser"], "email": a["email"]} for a in accounts
                ],
                "can_send": connected,
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
        """Show Gmail, or one Gmail link (e.g. an email just sent: "Open in Gmail"), in
        the browser it is signed in in; else in HireAce's own browser."""
        if link and urlparse(link).hostname not in _GOOGLE_HOSTS:
            raise GmailError("Only Gmail links can be opened.")
        if (await self.status())["state"] != "ready":
            accounts = await self._open_accounts()
            if accounts:
                await asyncio.to_thread(
                    os.startfile, accounts[0]["process"], "open", link or GMAIL_URL
                )
                return await self.status()
        await self._browser.open_url(link or GMAIL_URL)
        return await self.status()

    async def send(
        self, to: list[str], subject: str, text: str, attachments: list[str]
    ) -> dict:
        """Send a plain-text email from the signed-in account. Returns the sender."""
        status = await self.status()
        if status["state"] != "ready":
            return await self._send_in_user_browser(to, subject, text, attachments)
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

    async def _open_accounts(self) -> list[dict]:
        """The Gmail accounts open in any browser. Windows reports no tabs for a
        minimized browser window: its tabs from when it was last seen count."""
        windows = (await asyncio.to_thread(browser_tabs))["windows"]
        known = {}
        for window in windows:
            handle = window.get("window")
            window["tabs"] = window.get("tabs") or self._known_tabs.get(handle, [])
            known[handle] = window["tabs"]
        self._known_tabs = known
        return signed_in_accounts(windows)

    async def _send_in_user_browser(
        self, to: list[str], subject: str, text: str, attachments: list[str]
    ) -> dict:
        accounts = await self._open_accounts()
        if not accounts:
            raise GmailError(NOT_READY)
        account = accounts[0]
        query = urlencode(
            {
                "authuser": account["email"],
                "view": "cm",
                "fs": "1",
                "hl": "en",  # the script finds Gmail's buttons by their English names
                "to": ",".join(to),
                "su": subject,
                "body": text,
            }
        )
        url = f"https://mail.google.com/mail/?{query}"
        if len(url) > MAX_COMPOSE_URL:
            raise GmailError("The email is too long to send: shorten the message.")
        result = await asyncio.to_thread(
            send_in_browser,
            {
                "browser": account["process"],
                "email": account["email"],
                "url": url,
                "subject": subject,
                "files": attachments,
            },
        )
        if not result.get("sent"):
            raise GmailError(result.get("reason") or "Gmail did not send it.")
        return {"from": account["email"]}

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
