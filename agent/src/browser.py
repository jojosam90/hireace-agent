from __future__ import annotations

import asyncio
import contextlib
import re
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from playwright.async_api import (
    Locator,
    Page,
    async_playwright,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from local_desktop import focus_window_with_title


class BrowserError(Exception):
    """A user-facing browser operation failure."""


async def _bring_page_window_to_front(page: Page) -> None:
    marker = f"Jarvis Browser {uuid.uuid4().hex}"
    original_title = ""
    title_changed = False
    try:
        original_title = await page.title()
        await page.evaluate("title => { document.title = title; }", marker)
        title_changed = True
        await page.bring_to_front()
        await asyncio.to_thread(focus_window_with_title, marker)
    except Exception:
        # Foreground activation is best-effort and must not prevent browser use.
        return
    finally:
        if title_changed:
            with contextlib.suppress(Exception):
                await page.evaluate(
                    "title => { document.title = title; }",
                    original_title,
                )


# Element under a screen pixel + focused field + payment inputs, for the policy
# Screen pixels are physical; window geometry is in CSS pixels (Windows display scaling).
# Chrome's toolbar height is outer minus inner height (minus the bottom border, equal to the side).
_SCREEN_CONTEXT_JS = """([sx, sy]) => {
  const dpr = window.devicePixelRatio || 1;
  const border = (window.outerWidth - window.innerWidth) / 2;
  const ox = window.screenX + border;
  const oy = window.screenY + (window.outerHeight - window.innerHeight) - border;
  const describe = el => !el ? '' : (el.getAttribute('aria-label') || el.getAttribute('title') ||
    el.value || el.innerText || el.getAttribute('alt') || '').trim().replace(/\\s+/g, ' ').slice(0, 120);
  let target = '', inside = false;
  if (sx !== null && sy !== null) {
    const x = sx / dpr - ox, y = sy / dpr - oy;
    inside = x >= 0 && y >= 0 && x < window.innerWidth && y < window.innerHeight;
    if (inside) {
      const el = document.elementFromPoint(x, y);
      const control = el && el.closest('button, a, input, select, textarea, [role=button], [role=link]');
      target = describe(control || el);
    }
  }
  const active = document.hasFocus() ? document.activeElement : null;
  const field = active && /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName) ? {
    autocomplete: active.autocomplete || '', name: active.name || '', id: active.id || '',
    type: active.type || '',
    label: (active.labels && active.labels[0] && active.labels[0].innerText) ||
           active.getAttribute('aria-label') || active.placeholder || '',
  } : {};
  const payment_fields = [...document.querySelectorAll('input, select')].some(el =>
    /cc-|card.?number|cvv|cvc|security code|expir/.test(
      [el.autocomplete, el.name, el.id, el.getAttribute('aria-label'), el.placeholder].join(' ').toLowerCase()));
  return { target, inside, field, payment_fields, focused: document.hasFocus() };
}"""


# Sites whose open tab open_url switches to rather than opening again
_REUSE_TAB_HOSTS = {"mail.google.com", "outlook.office.com", "outlook.live.com"}


# Outline the element and pulse a ring at its centre (two for a double-click),
# so the user sees what the agent clicks. Removes itself after the animation.
_SHOW_CLICK_JS = """(el, rings) => {
  const r = el.getBoundingClientRect();
  const box = document.createElement('div');
  const style = (node, css) => Object.assign(node.style, css);
  style(box, {position: 'fixed', left: r.left - 3 + 'px', top: r.top - 3 + 'px',
    width: r.width + 6 + 'px', height: r.height + 6 + 'px', border: '3px solid #f59e0b',
    borderRadius: '6px', background: 'rgba(245,158,11,0.12)', zIndex: 2147483647,
    pointerEvents: 'none', boxSizing: 'border-box', transition: 'opacity 0.4s'});
  document.documentElement.appendChild(box);
  const cx = r.left + Math.min(r.width / 2, 120), cy = r.top + r.height / 2;
  const nodes = [box];
  for (let i = 0; i < rings; i++) {
    const ring = document.createElement('div');
    style(ring, {position: 'fixed', left: cx - 18 + 'px', top: cy - 18 + 'px',
      width: '36px', height: '36px', borderRadius: '50%', border: '4px solid #f59e0b',
      zIndex: 2147483647, pointerEvents: 'none', boxSizing: 'border-box'});
    document.documentElement.appendChild(ring);
    ring.animate([{transform: 'scale(0.3)', opacity: 1}, {transform: 'scale(1.6)', opacity: 0}],
      {duration: 600, delay: 150 + i * 250, fill: 'both'});
    nodes.push(ring);
  }
  setTimeout(() => { box.style.opacity = '0'; }, 1300);
  setTimeout(() => nodes.forEach(n => n.remove()), 1800);
}"""


async def _show_click(locator: Locator, double: bool) -> None:
    """Mark the target on the page, then pause briefly so the user sees it."""
    try:
        await locator.scroll_into_view_if_needed(timeout=2_000)
        await locator.evaluate(_SHOW_CLICK_JS, 2 if double else 1, timeout=2_000)
    except Exception:
        return  # Only a visual aid; never block the click
    await asyncio.sleep(0.5)


class BrowserManager:
    """Own one visible browser window for the agent.

    With ``profile_dir`` it runs installed Chrome on its own persistent profile,
    so sign-ins (Gmail, Outlook) survive restarts without touching the user's
    everyday Chrome profile. Without it, a throwaway Chromium (tests, headless).
    """

    def __init__(
        self,
        *,
        headless: bool = False,
        timeout_ms: int = 15_000,
        profile_dir: Path | None = None,
        channel: str | None = "chrome",
    ) -> None:
        self._headless = headless
        self._timeout_ms = timeout_ms
        self._profile_dir = profile_dir
        self._channel = channel
        self._playwright = None
        self._browser = None
        self._context = None
        self._page: Page | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._page is not None and not self._page.is_closed():
            return

        if self._playwright is None:
            self._playwright = await async_playwright().start()

        if self._context is None:
            if self._profile_dir is not None:
                self._context = (
                    await self._playwright.chromium.launch_persistent_context(
                        str(self._profile_dir),
                        channel=self._channel,
                        headless=self._headless,
                        no_viewport=True,
                        # Without the "controlled by automated software" markers:
                        # Google's sign-in page refuses browsers that show them, and
                        # the user signs in to Gmail in this window
                        ignore_default_args=["--enable-automation"],
                        args=[
                            "--start-maximized",
                            "--disable-blink-features=AutomationControlled",
                        ],
                    )
                )
            else:
                self._browser = await self._playwright.chromium.launch(
                    headless=self._headless,
                )
                self._context = await self._browser.new_context()
            # The user closed the window: start a fresh one on the next action
            self._context.on("close", lambda _context: self.reset())
        pages = self._open_pages()
        self._page = pages[0] if pages else await self._context.new_page()
        self._page.set_default_timeout(self._timeout_ms)
        if not self._headless:
            await _bring_page_window_to_front(self._page)

    async def close(self) -> None:
        async with self._lock:
            if self._context is not None:
                with contextlib.suppress(Exception):
                    await self._context.close()
            if self._browser is not None:
                await self._browser.close()
            if self._playwright is not None:
                await self._playwright.stop()

            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None

    async def open_url(self, url: str) -> dict[str, str]:
        self._validate_url(url)
        page = await self._get_page()

        async with self._lock:
            # Gmail already open in a tab: show that one instead of loading it again
            if urlparse(url).hostname in _REUSE_TAB_HOSTS:
                for tab in self._open_pages():
                    if urlparse(tab.url).hostname == urlparse(url).hostname:
                        self._page = tab
                        if self._headless:
                            await tab.bring_to_front()
                        else:
                            await _bring_page_window_to_front(tab)
                        return {**await self._page_summary(tab), "already_open": True}
            try:
                await page.goto(url, wait_until="domcontentloaded")
                return await self._page_summary(page)
            except PlaywrightTimeoutError as exc:
                raise BrowserError("The page took too long to load.") from exc
            except Exception as exc:
                raise BrowserError(f"I could not open that page: {exc}") from exc

    async def read_page(self, *, max_chars: int = 12_000) -> dict[str, str | bool]:
        page = await self._get_page()

        async with self._lock:
            try:
                text = await page.locator("body").inner_text(timeout=self._timeout_ms)
            except PlaywrightTimeoutError as exc:
                raise BrowserError(
                    "The page content was not available in time."
                ) from exc

            text = re.sub(r"\s+", " ", text).strip()
            truncated = len(text) > max_chars
            return {
                "url": page.url,
                "title": await page.title(),
                "text": text[:max_chars],
                "truncated": truncated,
            }

    async def inspect_page(self, *, max_chars: int = 8_000) -> dict[str, object]:
        """Return readable text plus a compact inventory of interactive elements."""
        page = await self._get_page()

        async with self._lock:
            try:
                text = await page.locator("body").inner_text(timeout=self._timeout_ms)
                elements = await page.locator(
                    "button, a, input, textarea, select, [role]"
                ).evaluate_all(
                    """elements => elements
                      .filter(element => {
                        const style = window.getComputedStyle(element);
                        return style.display !== 'none' && style.visibility !== 'hidden';
                      })
                      .slice(0, 80)
                      .map((element, index) => ({
                        index,
                        tag: element.tagName.toLowerCase(),
                        role: element.getAttribute('role') || '',
                        name: (element.getAttribute('aria-label') ||
                          element.getAttribute('title') ||
                          (element.labels && element.labels[0] && element.labels[0].innerText) ||
                          element.getAttribute('placeholder') ||
                          element.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 120),
                        type: element.getAttribute('type') || '',
                      }))"""
                )
            except PlaywrightTimeoutError as exc:
                raise BrowserError("The page could not be inspected in time.") from exc

            text = re.sub(r"\s+", " ", text).strip()
            return {
                "url": page.url,
                "title": await page.title(),
                "text": text[:max_chars],
                "elements": elements,
            }

    async def go_back(self) -> dict[str, str]:
        page = await self._get_page()

        async with self._lock:
            try:
                await page.go_back(wait_until="domcontentloaded")
                return await self._page_summary(page)
            except PlaywrightTimeoutError as exc:
                raise BrowserError("The previous page took too long to load.") from exc
            except Exception as exc:
                raise BrowserError(f"I could not go back: {exc}") from exc

    async def take_screenshot(self) -> dict[str, str | int | bool]:
        page = await self._get_page()

        async with self._lock:
            try:
                image = await page.screenshot(type="png")
                return {
                    "captured": True,
                    "url": page.url,
                    "bytes": len(image),
                }
            except Exception as exc:
                raise BrowserError(f"I could not capture the page: {exc}") from exc

    async def click(self, target: str, double: bool = False) -> dict[str, str]:
        page = await self._get_page()

        async with self._lock:
            locator = await self._resolve_target(page, target)
            # DevTools input, not the real mouse: works while the user uses the PC
            try:
                await _show_click(locator, double)
                if double:
                    await locator.dblclick(timeout=10_000)
                else:
                    await locator.click(timeout=10_000)
            except PlaywrightTimeoutError as exc:
                raise BrowserError(
                    f"The control {target!r} did not become clickable in time."
                ) from exc
            except Exception as exc:
                raise BrowserError(f"I could not click {target!r}: {exc}") from exc

            with contextlib.suppress(PlaywrightTimeoutError):
                await page.wait_for_load_state("domcontentloaded", timeout=5_000)

            return await self._page_summary(page)

    async def type_text(self, target: str, text: str) -> dict[str, str]:
        page = await self._get_page()

        async with self._lock:
            locator = await self._resolve_textbox(page, target)
            try:
                await locator.fill(text, timeout=5_000)
            except Exception as exc:
                raise BrowserError(f"I could not type into {target!r}: {exc}") from exc

            return {"target": target, "url": page.url}

    # --- Tabs ---------------------------------------------------------------------

    async def list_tabs(self) -> dict[str, object]:
        page = await self._get_page()
        tabs = [
            {"index": i, "title": await p.title(), "url": p.url, "active": p is page}
            for i, p in enumerate(self._open_pages())
        ]
        return {"tabs": tabs}

    async def switch_tab(self, index: int) -> dict[str, str]:
        await self._get_page()
        pages = self._open_pages()
        if not 0 <= int(index) < len(pages):
            raise BrowserError(
                f"There is no tab number {index}; there are {len(pages)} tabs."
            )
        async with self._lock:
            self._page = pages[int(index)]
            await self._page.bring_to_front()
            return await self._page_summary(self._page)

    async def close_tab(self) -> dict[str, object]:
        page = await self._get_page()
        async with self._lock:
            await page.close()
            remaining = self._open_pages()
            self._page = remaining[-1] if remaining else await self._context.new_page()
            self._page.set_default_timeout(self._timeout_ms)
            await self._page.bring_to_front()
            return {"closed": True, "now_showing": await self._page_summary(self._page)}

    async def new_tab(self, url: str = "") -> dict[str, str]:
        if url:
            self._validate_url(url)
        await self._get_page()
        async with self._lock:
            self._page = await self._context.new_page()
            self._page.set_default_timeout(self._timeout_ms)
            await self._page.bring_to_front()
            if url:
                await self._page.goto(url, wait_until="domcontentloaded")
            return await self._page_summary(self._page)

    def _open_pages(self) -> list[Page]:
        return (
            [p for p in self._context.pages if not p.is_closed()]
            if self._context
            else []
        )

    # --- For gmail.py: the window's tabs, without opening the window ---------------

    @property
    def running(self) -> bool:
        if self._browser is not None and not self._browser.is_connected():
            self.reset()
        return self._context is not None

    def pages(self) -> list[Page]:
        return self._open_pages()

    async def new_page(self) -> Page:
        """A new tab in this window (starting the window if needed)."""
        await self._get_page()
        page = await self._context.new_page()
        page.set_default_timeout(self._timeout_ms)
        return page

    # --- Policy context for screen-coordinate actions -----------------------------

    async def screen_context(self, x: int | None = None, y: int | None = None) -> dict:
        """What the browser shows at a screen pixel, and its focused field.

        Never launches the browser: returns {} when its window is not open.
        """
        page = self._page
        if page is None or page.is_closed():
            return {}
        async with self._lock:
            info = await page.evaluate(_SCREEN_CONTEXT_JS, [x, y])
            info["url"] = page.url
            return info

    async def scroll(self, direction: Literal["up", "down"]) -> dict[str, str]:
        if direction not in {"up", "down"}:
            raise BrowserError("Scroll direction must be 'up' or 'down'.")

        page = await self._get_page()
        amount = -650 if direction == "up" else 650

        async with self._lock:
            await page.mouse.wheel(0, amount)
            return {"direction": direction, "url": page.url}

    async def press_key(self, key: str) -> dict[str, str]:
        allowed_keys = {
            "Enter",
            "Escape",
            "Tab",
            "ArrowDown",
            "ArrowLeft",
            "ArrowRight",
            "ArrowUp",
            "Backspace",
        }
        if key not in allowed_keys:
            raise BrowserError("That keyboard key is not allowed.")

        page = await self._get_page()
        async with self._lock:
            await page.keyboard.press(key)
            return {"key": key, "url": page.url}

    async def open_browser(self) -> dict[str, str]:
        """Start (or reconnect to) the browser and bring up a page."""
        page = await self._get_page()
        async with self._lock:
            return await self._page_summary(page)

    async def close_browser(self) -> dict[str, bool]:
        """Close the browser window. The next browser action starts it again."""
        async with self._lock:
            with contextlib.suppress(Exception):
                if self._context is not None:
                    await self._context.close()
                if self._browser is not None:
                    await self._browser.close()
            self._page = None
            self._context = None
            self._browser = None
            return {"closed": True}

    async def page_context(self) -> dict[str, object]:
        """URL and whether the page has payment-card inputs (for the safety policy)."""
        page = await self._get_page()
        async with self._lock:
            try:
                payment_fields = await page.evaluate(
                    """() => [...document.querySelectorAll('input, select')].some(el => {
                      const s = [el.autocomplete, el.name, el.id,
                                 el.getAttribute('aria-label'), el.placeholder]
                        .join(' ').toLowerCase();
                      return /cc-|card.?number|cvv|cvc|security code|expir/.test(s);
                    })"""
                )
            except Exception:
                payment_fields = False
            return {"url": page.url, "payment_fields": bool(payment_fields)}

    async def field_attributes(self, target: str) -> dict[str, str]:
        """Attributes of the text field ``type_text`` would fill (for the safety policy)."""
        page = await self._get_page()
        async with self._lock:
            locator = await self._resolve_textbox(page, target)
            return await locator.evaluate(
                """el => ({
                  autocomplete: el.autocomplete || '',
                  name: el.name || '',
                  id: el.id || '',
                  type: el.type || '',
                  label: (el.labels && el.labels[0] && el.labels[0].innerText) ||
                         el.getAttribute('aria-label') || el.placeholder || '',
                })"""
            )

    def reset(self) -> None:
        """Forget the current window (e.g. the user closed it); the next action reopens it."""
        self._page = None
        self._context = None
        self._browser = None

    async def _get_page(self) -> Page:
        if self._browser is not None and not self._browser.is_connected():
            self.reset()
        if self._page is None or self._page.is_closed():
            await self.start()
        assert self._page is not None
        return self._page

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise BrowserError("Only complete http or https URLs can be opened.")
        if parsed.username or parsed.password:
            raise BrowserError("URLs containing embedded credentials are not allowed.")

    @staticmethod
    async def _page_summary(page: Page) -> dict[str, str]:
        return {"url": page.url, "title": await page.title()}

    async def _resolve_target(self, page: Page, target: str) -> Locator:
        candidates = []
        for role in ("button", "link", "tab", "menuitem", "checkbox", "radio"):
            candidates.append(page.get_by_role(role, name=target, exact=True))
            candidates.append(page.get_by_role(role, name=target, exact=False))
        candidates.append(page.get_by_text(target, exact=True))
        candidates.append(page.get_by_text(target, exact=False))

        locator = await _first_visible(candidates)
        if locator is None:
            raise BrowserError(f"I could not find a visible control named {target!r}.")
        return locator

    async def _resolve_textbox(self, page: Page, target: str) -> Locator:
        candidates = [
            page.get_by_role("textbox", name=target, exact=True),
            page.get_by_role("textbox", name=target, exact=False),
            page.get_by_role("searchbox", name=target, exact=False),
            page.get_by_label(target, exact=True),
            page.get_by_label(target, exact=False),
            page.get_by_placeholder(target, exact=True),
            page.get_by_placeholder(target, exact=False),
        ]
        normalized_target = target.casefold()
        if any(
            word in normalized_target for word in ("search", "query", "input", "text")
        ):
            candidates += [
                page.locator(selector)
                for selector in (
                    "input[type='search']",
                    "input[aria-label*='search' i]",
                    "input[placeholder*='search' i]",
                    "textarea",
                    "input:not([type=hidden])",
                )
            ]

        locator = await _first_visible(candidates)
        if locator is not None:
            return locator

        raise BrowserError(f"I could not find a text field named {target!r}.")


async def _first_visible(candidates: list[Locator]) -> Locator | None:
    """First visible match of the first candidate that has one.

    Pages often hold hidden copies of a control (collapsed menus, mobile
    layouts); clicking one of those waits until it times out.
    """
    for locator in candidates:
        visible = locator.filter(visible=True)
        if await visible.count():
            return visible.first
    return None
