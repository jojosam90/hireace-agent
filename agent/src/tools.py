import asyncio
import logging
import re
from urllib.parse import urlencode

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError

from action_backend import LocalBackend, RemoteBackend
from browser import BrowserManager
from policy import ALLOW, PageContext, decide

logger = logging.getLogger("jarvis.tools")

# Actions where the model names a control it guesses is there
GUESSING_ACTIONS = {"click", "type_text", "press_key"}
WARN_FAILURES = 3
HARD_STOP_FAILURES = 5


def approval_reminder(summary: str) -> str:
    """What the agent says when an Approve button appears, e.g. "Please approve: save
    Q-00002 as Excel and PDF. Tap Approve on screen, or say yes." """
    action = summary.strip().rstrip(".") or "this step"
    return f"Please approve: {action}. Tap Approve on screen, or say yes."


APPROVAL_INSTRUCTIONS = (
    "This action needs the user's approval and an Approve button is now on screen. "
    "Say say_now out loud right away, in one short sentence, then wait: call no other "
    "tool. As soon as they say yes in any words, call approve_action (the "
    "approval_id may be left empty); do not ask again. If they say no, call "
    "deny_action. If they tap Approve you will be told; do not call approve_action "
    "then. If nothing happens, remind them once more."
)


_BARE_HOST = re.compile(r"^(localhost|[\w-]+(\.[\w-]+)+)(:\d+)?(/\S*)?$")


def normalize_url(url: str) -> str:
    """Add https:// to bare domains ("trip.com", "www.google.com/maps").

    Anything else (other schemes, free text) is returned unchanged so the
    browser's URL validation can reject it.
    """
    url = url.strip()
    if "://" not in url and _BARE_HOST.match(url):
        return f"https://{url}"
    return url


def duckduckgo_search_url(query: str) -> str:
    query = query.strip()
    if not query:
        raise ValueError("The search query cannot be empty.")
    return f"https://duckduckgo.com/?{urlencode({'q': query})}"


class BrowserTools:
    """Browser tools for the agent. Every action goes through the gatekeeper policy."""

    def __init__(self, backend: LocalBackend | RemoteBackend | BrowserManager) -> None:
        if isinstance(backend, BrowserManager):
            backend = LocalBackend(backend)
        self.backend = backend
        self._watchers: set[asyncio.Task] = set()
        self._failures = 0  # failed actions in a row
        # Second agent that reads the screen in parallel (screen_helper.py), if any
        self.screen_helper = None

    @property
    def tools(self) -> list:
        return [
            self.open_url,
            self.search_the_web,
            self.read_page,
            self.inspect_page,
            self.go_back,
            self.take_screenshot,
            self.click,
            self.approve_action,
            self.deny_action,
            self.type_text,
            self.scroll,
            self.press_key,
            self.open_browser,
            self.close_browser,
        ]

    async def _run(self, context: RunContext | None, action: str, args: dict):
        # A model that keeps guessing control names can click on for minutes
        # (seen with a full-page ad covering the page): after a few failures in
        # a row, stop page interactions until something else succeeds.
        if action in GUESSING_ACTIONS and self._failures >= HARD_STOP_FAILURES:
            raise ToolError(
                f"Not attempted: the last {self._failures} actions failed. Stop trying "
                "controls. Tell the user what went wrong and ask how to proceed, or "
                "read_page / take_screenshot to see what is on the page."
            )
        outcome = await self.backend.submit(action, args)
        status = outcome.get("status")
        if status == "done":
            self._failures = 0
            if self.screen_helper is not None and context is not None:
                self.screen_helper.after_action(context.session, action)
            return outcome.get("result", {})
        if status == "denied":
            raise ToolError(f"Blocked by the safety policy: {outcome.get('reason')}")
        if status == "needs_approval":
            self._failures = 0
            if context is not None:
                # The watcher resumes the task when the user taps Approve; a
                # spoken "yes" goes to approve_action
                self._watch_web_approval(
                    context, outcome["approval_id"], outcome["summary"]
                )
            # Spoken, never a silent wait: the user may not be looking at the screen
            return {
                "status": "needs_approval",
                "approval_id": outcome["approval_id"],
                "action": outcome["summary"],
                "say_now": approval_reminder(outcome["summary"]),
                "instructions": APPROVAL_INSTRUCTIONS,
            }
        self._failures += 1
        reason = str(outcome.get("reason", "The action failed."))
        if self._failures >= WARN_FAILURES:
            reason += (
                f" ({self._failures} failed actions in a row: do not keep guessing. "
                "Look at the page or tell the user and ask how to proceed.)"
            )
        raise ToolError(reason)

    def _watch_web_approval(self, context: RunContext, approval_id: str, summary: str):
        """Tell the agent when the user resolves an approval in the web app."""
        session = context.session

        async def watch() -> None:
            for _ in range(130):
                await asyncio.sleep(1)
                info = await self.backend.status(approval_id)
                state = info.get("state")
                if state in (None, "pending"):
                    continue
                if info.get("resolved_by") == "web":
                    if state == "done":
                        instructions = (
                            f"The user approved '{summary}' in the app and it ran "
                            f"(result: {info.get('result')}). Continue the task where you "
                            "left off; nothing else needs approval during this call."
                        )
                    else:
                        instructions = (
                            f"The user's answer to '{summary}' was: {state}. It did not "
                            "run. Say so in a few words and offer A/B options."
                        )
                    session.generate_reply(instructions=instructions)
                return

        task = asyncio.create_task(watch())
        self._watchers.add(task)
        task.add_done_callback(self._watchers.discard)

    @function_tool()
    async def search_the_web(
        self,
        context: RunContext,
        query: str,
    ) -> dict[str, str]:
        """Open fallback DuckDuckGo results in the agent-controlled browser.

        Use this only when the user needs a general internet search and did not name a
        website, service, or domain. If the user names a destination, open its official
        URL directly with open_url instead. Read or inspect the resulting page before
        answering the user.

        Args:
            query: A concise DuckDuckGo search query containing all relevant context.
        """
        try:
            url = duckduckgo_search_url(query)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        return await self._run(context, "open_url", {"url": url})

    @function_tool()
    async def open_url(self, context: RunContext, url: str) -> dict[str, str]:
        """Open a public webpage directly in the agent-controlled browser.

        Prefer this over DuckDuckGo whenever the user names a website, service, domain,
        or specific destination. Use the destination's official URL.

        Args:
            url: A complete http or https URL to open.
        """
        return await self._run(context, "open_url", {"url": normalize_url(url)})

    @function_tool()
    async def read_page(self, context: RunContext) -> dict[str, str | bool]:
        """Read the visible text from the current browser page."""
        return await self._run(context, "read_page", {})

    @function_tool()
    async def inspect_page(self, context: RunContext) -> dict[str, object]:
        """Inspect the current page, including readable text and interactive element names.

        Use this before clicking or typing so you can choose a visible control by its
        returned name or role.
        """
        return await self._run(context, "inspect_page", {})

    @function_tool()
    async def go_back(self, context: RunContext) -> dict[str, str]:
        """Go back to the previous page in the agent-controlled browser."""
        return await self._run(context, "go_back", {})

    @function_tool()
    async def take_screenshot(self, context: RunContext) -> dict[str, str | int | bool]:
        """Capture the current browser page for diagnostics."""
        return await self._run(context, "take_screenshot", {})

    @function_tool()
    async def click(
        self, context: RunContext, target: str, double: bool = False
    ) -> dict[str, str]:
        """Click a visible control or text by its name; the click is shown on the page.

        Consequential clicks (send, submit, delete...) return needs_approval instead of
        running. Payment actions are always blocked.

        Args:
            target: The visible or accessible name of the control, or visible text
                (e.g. an email's subject or sender in Gmail).
            double: Double-click instead, e.g. to open an email in the Gmail inbox.
        """
        args = {"target": target, **({"double": True} if double else {})}
        return await self._run(context, "click", args)

    async def _resolve(self, approval_id: str, *, approve: bool) -> dict:
        # The model sometimes loses or garbles the id: fall back to what is waiting
        if approval_id:
            outcome = await self.backend.resolve(approval_id, approve=approve)
            if outcome.get("status") != "unknown":
                return outcome
        waiting = await self.backend.pending()
        if not waiting:
            raise ToolError("Nothing is waiting for approval.")
        return await self.backend.resolve(waiting[-1]["id"], approve=approve)

    @function_tool()
    async def approve_action(self, context: RunContext, approval_id: str = "") -> dict:
        """Run the action that is waiting for approval, as soon as the user says yes.

        Any yes counts ("yes", "ok", "go ahead", "approved", "好", "可以").

        Args:
            approval_id: The approval_id from needs_approval; leave empty for the one waiting now.
        """
        outcome = await self._resolve(approval_id, approve=True)
        if outcome.get("status") == "done":
            return outcome.get("result", {})
        raise ToolError(f"The action did not run: {outcome}")

    @function_tool()
    async def deny_action(self, context: RunContext, approval_id: str = "") -> str:
        """Cancel the action that is waiting for approval, because the user said no.

        Args:
            approval_id: The approval_id from needs_approval; leave empty for the one waiting now.
        """
        await self._resolve(approval_id, approve=False)
        return "Cancelled."

    @function_tool()
    async def type_text(
        self,
        context: RunContext,
        target: str,
        text: str,
    ) -> dict[str, str]:
        """Fill a visible text field by its label, placeholder, or accessible name.

        Args:
            target: The label, placeholder, or accessible name of the text field.
            text: The text to enter.
        """
        return await self._run(context, "type_text", {"target": target, "text": text})

    @function_tool()
    async def scroll(self, context: RunContext, direction: str) -> dict[str, str]:
        """Scroll the current browser page up or down.

        Args:
            direction: Either 'up' or 'down'.
        """
        return await self._run(context, "scroll", {"direction": direction})

    @function_tool()
    async def press_key(self, context: RunContext, key: str) -> dict[str, str]:
        """Press a safe navigation key in the current browser page.

        Args:
            key: One of Enter, Escape, Tab, an arrow key, or Backspace.
        """
        return await self._run(context, "press_key", {"key": key})

    @function_tool()
    async def open_browser(self, context: RunContext) -> dict[str, str]:
        """Open your browser window (Chrome) without opening a page.

        Use only when the user asks to open or start the browser itself. Other
        browser tools start the browser automatically.
        """
        return await self._run(context, "open_browser", {})

    @function_tool()
    async def close_browser(self, context: RunContext) -> dict[str, bool]:
        """Close your browser window."""
        return await self._run(context, "close_browser", {})

    @staticmethod
    def _requires_confirmation(target: str) -> bool:
        return decide("click", {"target": target}, PageContext()).verdict != ALLOW
