"""Control of the user's own Windows computer: tabs, mouse, keyboard, windows, vision.

Every action goes through the gatekeeper (same policy as the browser tools).
After screen actions the agent is shown a fresh screenshot of the screen, so it
can see the result and aim the next click; coordinates use a 0-1000
scale across the screen.
"""

from __future__ import annotations

import io
import logging

from livekit import rtc
from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError
from PIL import Image

from tools import BrowserTools, normalize_url

logger = logging.getLogger("jarvis.desktop")


class DesktopTools:
    def __init__(self, browser_tools: BrowserTools) -> None:
        self._browser_tools = browser_tools
        self.backend = browser_tools.backend

    @property
    def tools(self) -> list:
        return [
            self.list_tabs,
            self.new_tab,
            self.switch_tab,
            self.close_tab,
            self.look_at_screen,
            self.click_on_screen,
            self.move_mouse,
            self.drag_on_screen,
            self.scroll_screen,
            self.type_on_screen,
            self.press_keys,
            self.list_windows,
            self.focus_window,
            self.find_browser_tab,
            self.open_browser_item,
            self.read_browser_window,
            self.close_window,
            self.open_app,
            self.find_files,
            self.open_file,
            self.ask_screen_helper,
        ]

    async def _run(self, context: RunContext, action: str, args: dict, *, show: bool):
        result = await self._browser_tools._run(context, action, args)
        if show and not (
            isinstance(result, dict) and result.get("status") == "needs_approval"
        ):
            await self._show_screen(context)
        return result

    async def _show_screen(self, context: RunContext) -> bool:
        """Send the current screen to the model as a video frame."""
        # A 1280px JPEG is a fraction of a full-size PNG: quicker to capture, send
        # and for the model to read, and still sharp enough to aim clicks
        jpeg = await self.backend.screenshot(format="jpeg", quality=75, width=1280)
        if not jpeg:
            return False
        try:
            image = Image.open(io.BytesIO(jpeg)).convert("RGBA")
            frame = rtc.VideoFrame(
                image.width, image.height, rtc.VideoBufferType.RGBA, image.tobytes()
            )
            context.session.current_agent.realtime_llm_session.push_video(frame)
            return True
        except Exception:
            logger.exception("could not show the screen to the model")
            return False

    # --- Browser tabs -------------------------------------------------------------

    @function_tool()
    async def list_tabs(self, context: RunContext) -> dict:
        """List the open browser tabs with their index, title and address."""
        return await self._run(context, "list_tabs", {}, show=False)

    @function_tool()
    async def new_tab(self, context: RunContext, url: str = "") -> dict:
        """Open a new browser tab, optionally loading a page in it.

        Args:
            url: Optional complete http or https URL to open in the new tab.
        """
        url = normalize_url(url) if url else url
        return await self._run(context, "new_tab", {"url": url}, show=False)

    @function_tool()
    async def switch_tab(self, context: RunContext, index: int) -> dict:
        """Switch to another browser tab by its index from list_tabs.

        Args:
            index: The tab index (0 is the first tab).
        """
        return await self._run(context, "switch_tab", {"index": index}, show=False)

    @function_tool()
    async def close_tab(self, context: RunContext) -> dict:
        """Close the current browser tab (the web page the user is looking at)."""
        return await self._run(context, "close_tab", {}, show=False)

    # --- Screen (mouse, keyboard, vision) -----------------------------------------

    @function_tool()
    async def look_at_screen(self, context: RunContext) -> str:
        """Look at the user's computer screen.

        Use before clicking by screen position, to check what is on screen, or to
        verify the result of an action. Not needed after screen actions, which show
        the updated screen automatically.
        """
        if not await self._show_screen(context):
            raise ToolError("The screen is not available.")
        return "You can now see the current screen."

    @function_tool()
    async def click_on_screen(
        self,
        context: RunContext,
        x: float,
        y: float,
        button: str = "left",
        double: bool = False,
    ) -> dict:
        """Move the real mouse to a point on the screen and click it.

        Use for desktop apps, icons, or anything the page tools cannot target. For
        web page controls prefer click, which finds them by name.

        Args:
            x: Horizontal position on a 0-1000 scale across the screen (0,0 top-left, 1000,1000 bottom-right), estimated from the latest screen image.
            y: Vertical position on a 0-1000 scale across the screen (0,0 top-left, 1000,1000 bottom-right), estimated from the latest screen image.
            button: "left", "right" or "middle".
            double: True for a double-click (e.g. opening a desktop icon).
        """
        args = {"x": x, "y": y, "button": button, "clicks": 2 if double else 1}
        return await self._run(context, "screen_click", args, show=True)

    @function_tool()
    async def move_mouse(self, context: RunContext, x: float, y: float) -> dict:
        """Move the real mouse pointer to a point without clicking (e.g. to hover).

        Args:
            x: Horizontal position on a 0-1000 scale across the screen (0,0 top-left, 1000,1000 bottom-right), estimated from the latest screen image.
            y: Vertical position on a 0-1000 scale across the screen (0,0 top-left, 1000,1000 bottom-right), estimated from the latest screen image.
        """
        return await self._run(context, "screen_move", {"x": x, "y": y}, show=True)

    @function_tool()
    async def drag_on_screen(
        self, context: RunContext, x: float, y: float, to_x: float, to_y: float
    ) -> dict:
        """Press the mouse at one point, drag to another and release.

        Args:
            x: Start horizontal position on a 0-1000 scale across the screen (0,0 top-left, 1000,1000 bottom-right), estimated from the latest screen image.
            y: Start vertical position on a 0-1000 scale across the screen (0,0 top-left, 1000,1000 bottom-right), estimated from the latest screen image.
            to_x: End horizontal position, same scale.
            to_y: End vertical position, same scale.
        """
        args = {"x": x, "y": y, "to_x": to_x, "to_y": to_y}
        return await self._run(context, "screen_drag", args, show=True)

    @function_tool()
    async def scroll_screen(
        self,
        context: RunContext,
        direction: str,
        amount: int = 5,
        x: float | None = None,
        y: float | None = None,
    ) -> dict:
        """Scroll with the mouse wheel, optionally over a specific point.

        Args:
            direction: "up" or "down".
            amount: How far to scroll (1-20 wheel steps).
            x: Optional horizontal position to scroll over, on a 0-1000 scale across the screen (0,0 top-left, 1000,1000 bottom-right), estimated from the latest screen image.
            y: Optional vertical position to scroll over, same scale.
        """
        args: dict = {"direction": direction, "amount": max(1, min(int(amount), 20))}
        if x is not None and y is not None:
            args.update(x=x, y=y)
        return await self._run(context, "screen_scroll", args, show=True)

    @function_tool()
    async def type_on_screen(self, context: RunContext, text: str) -> dict:
        """Type text with the real keyboard into whatever currently has focus.

        Click the target field first. For web page fields prefer type_text.

        Args:
            text: The text to type (any language).
        """
        return await self._run(context, "screen_type", {"text": text}, show=True)

    @function_tool()
    async def press_keys(self, context: RunContext, keys: str) -> dict:
        """Press a key or keyboard shortcut on the user's computer.

        Args:
            keys: A key or combination joined with +, for example "enter", "esc",
                "tab", "ctrl+t" (new tab), "ctrl+w" (close tab), "ctrl+l" (address
                bar), "alt+tab", "ctrl+c", "ctrl+v", "pagedown".
        """
        return await self._run(context, "screen_key", {"keys": keys}, show=True)

    # --- Windows and apps ---------------------------------------------------------

    @function_tool()
    async def list_windows(self, context: RunContext) -> dict:
        """List the open windows on the user's computer."""
        return await self._run(context, "list_windows", {}, show=False)

    @function_tool()
    async def focus_window(self, context: RunContext, title: str) -> dict:
        """Bring a window to the front.

        Args:
            title: Part of the window title, from list_windows.
        """
        return await self._run(context, "focus_window", {"title": title}, show=True)

    @function_tool()
    async def find_browser_tab(self, context: RunContext, text: str) -> dict:
        """Find a tab in any open browser (Chrome, Edge, Firefox, Brave, Opera, and
        your own browser), switch to it and bring it to the front, in one quick step.
        Checks every tab, not only the one each window is showing.

        Args:
            text: Part of the tab's name, e.g. "Gmail" or "Inbox".
        """
        return await self._run(context, "find_browser_tab", {"text": text}, show=True)

    @function_tool()
    async def open_browser_item(self, context: RunContext, text: str) -> dict:
        """Open an email in the Gmail inbox (or a row in a list in any browser): finds
        the row by its text and double-clicks it with the mouse, so the user sees it.
        Works in the user's own browser windows. Returns the opened email's exact text
        (page_text): take every number and name from it, not from the screen image.

        Args:
            text: Words from the row, e.g. the sender or part of the subject ("Palm
                Garden"), or "unread" for the topmost unread email.
        """
        return await self._run(context, "open_browser_item", {"text": text}, show=True)

    @function_tool()
    async def read_browser_window(self, context: RunContext, text: str = "") -> dict:
        """Read the exact text of a page open in any browser window, e.g. an email open
        in the user's Gmail. Use it for every number, name and address you take from
        an email (quantities, prices, phone numbers): reading them off the screen
        image gets them wrong.

        Args:
            text: Part of the window's title, e.g. the email's subject ("Seaview");
                leave empty for the browser window in front.
        """
        return await self._run(
            context, "read_browser_window", {"text": text}, show=False
        )

    @function_tool()
    async def close_window(self, context: RunContext, title: str) -> dict:
        """Close a window on the user's computer (needs their approval; the app may ask to save).

        Args:
            title: Part of the window title, from list_windows.
        """
        return await self._run(context, "close_window", {"title": title}, show=True)

    @function_tool()
    async def open_app(self, context: RunContext, app: str) -> dict:
        """Open a desktop app on the user's computer.

        For the web browser use open_browser or open_url instead.

        Args:
            app: One of "word", "excel", "powerpoint", "outlook", "notepad",
                "files" (File Explorer) or "calculator".
        """
        return await self._run(context, "open_app", {"app": app}, show=True)

    # --- Screen helper (a second agent with its own eyes) ---------------------------

    @function_tool()
    async def ask_screen_helper(
        self, context: RunContext, question: str, wait: bool = False
    ) -> str:
        """Ask your screen helper, a second agent that reads the screen, a question about it.

        By default it looks in the background while you keep talking to the user,
        and its answer reaches you a moment later. Set wait=True when you need the
        answer before your next step. Examples: "Is the Acme proposal open in
        Word?", "Is there a dialog or error?", "Where is the Save button?" (it
        answers with 0-1000 coordinates for click_on_screen).

        Args:
            question: What to find out about the screen.
            wait: True to wait for the answer (about 2 seconds) instead of getting it later.
        """
        helper = self._browser_tools.screen_helper
        if helper is None:
            raise ToolError("The screen helper is not available.")
        if wait:
            return await helper.look(question)
        helper.ask_in_background(context.session, question)
        return "Your screen helper is looking; its answer will reach you shortly. Carry on meanwhile."

    # --- Files --------------------------------------------------------------------

    @function_tool()
    async def find_files(
        self, context: RunContext, query: str, kind: str = "any"
    ) -> dict:
        """Search the user's computer for files or folders by name, newest first.

        Looks in Desktop, Documents, Downloads, OneDrive and the other drives. Then
        open the right one with open_file. If several plausible files match, tell
        the user the best few (name, folder, date) and ask which one.

        Args:
            query: Words from the file name, for example "acme proposal". Leave out
                the file type and filler words like "file" or "my".
            kind: "any", "word", "excel", "powerpoint", "pdf", "image" or "folder".
        """
        return await self._run(
            context, "find_files", {"query": query, "kind": kind}, show=False
        )

    @function_tool()
    async def open_file(self, context: RunContext, path: str) -> dict:
        """Open a file in its usual app (Word, Excel, PowerPoint, PDF viewer...) or a folder in File Explorer.

        Args:
            path: The full path exactly as returned by find_files.
        """
        return await self._run(context, "open_file", {"path": path}, show=True)
