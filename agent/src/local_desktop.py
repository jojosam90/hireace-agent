"""Mouse, keyboard, windows, files and screenshots on this Windows PC.

Only the gatekeeper uses this; the agent never touches the desktop directly.
Slamming the mouse into a screen corner is an emergency stop: pyautogui's
fail-safe trips, and every desktop action is refused for a while after.
"""

from __future__ import annotations

import asyncio
import datetime
import io
import json
import os
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw

# App names the model may use -> what `start` launches (Windows App Paths).
# Keep in sync with DESKTOP_APPS in policy.py.
APPS = {
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "outlook": "outlook",
    "notepad": "notepad",
    "files": "explorer",
    "calculator": "calc",
}

EMERGENCY_STOP_SECONDS = 60

_KEY_ALIASES = {
    "control": "ctrl",
    "return": "enter",
    "escape": "esc",
    "del": "delete",
    "windows": "win",
    "cmd": "win",
    "pgdn": "pagedown",
    "pgup": "pageup",
    "arrowup": "up",
    "arrowdown": "down",
    "arrowleft": "left",
    "arrowright": "right",
}


class DesktopError(Exception):
    """A user-facing desktop operation failure."""


# --- Finding files -----------------------------------------------------------------

FILE_KINDS = {
    "word": {".docx", ".doc", ".docm", ".rtf", ".odt"},
    "excel": {".xlsx", ".xls", ".xlsm", ".xlsb", ".csv", ".ods"},
    "powerpoint": {".pptx", ".ppt", ".pptm", ".odp"},
    "pdf": {".pdf"},
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic"},
}

# Never worth searching, and often huge
_SKIP_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    ".cache",
    "appdata",
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "$recycle.bin",
    "system volume information",
    "recovery",
}


def _other_fixed_drives() -> list[Path]:
    """Fixed drives other than the Windows one (D:\\, F:\\...), where work files often live."""
    if sys.platform != "win32":
        return []
    import ctypes

    system = os.environ.get("SYSTEMDRIVE", "C:").upper()
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    drives = []
    for i in range(26):
        letter = f"{chr(65 + i)}:"
        if (
            mask & (1 << i)
            and letter != system
            and ctypes.windll.kernel32.GetDriveTypeW(f"{letter}\\") == 3  # DRIVE_FIXED
        ):
            drives.append(Path(f"{letter}\\"))
    return drives


def search_roots() -> list[Path]:
    """Where find_files looks: HIREACE_SEARCH_DIRS (;-separated) if set, else the
    user's Desktop, Documents, Downloads and OneDrive plus the other fixed drives."""
    if extra := os.environ.get("HIREACE_SEARCH_DIRS"):
        roots = [Path(p.strip()) for p in extra.split(";") if p.strip()]
    else:
        home = Path.home()
        roots = [home / "Desktop", home / "Documents", home / "Downloads"]
        roots += sorted(home.glob("OneDrive*"))
        roots += _other_fixed_drives()
    return [root for root in dict.fromkeys(roots) if root.is_dir()]


def find_files(
    query: str,
    roots: list[Path],
    *,
    kind: str = "any",
    limit: int = 10,
    time_budget: float = 10.0,
) -> dict:
    """Files (or folders, kind="folder") whose name contains every word of query.

    Breadth-first, so shallow matches are found before the time budget runs out;
    documents come first, newest first.
    """
    words = query.casefold().split()
    if not words:
        raise DesktopError("Say which file to look for.")
    if kind not in FILE_KINDS and kind not in ("any", "folder"):
        raise DesktopError(
            f"Unknown kind {kind!r}; use any, folder or {sorted(FILE_KINDS)}."
        )
    extensions = FILE_KINDS.get(kind)

    matches: dict[str, os.DirEntry] = {}
    queue = deque(roots)
    deadline = time.monotonic() + time_budget
    complete = True
    while queue:
        if time.monotonic() > deadline:
            complete = False
            break
        try:
            entries = os.scandir(queue.popleft())
        except OSError:
            continue
        with entries:
            for entry in entries:
                name = entry.name
                if name.startswith(
                    (".", "~$", "$")
                ):  # hidden, Office lock files, system
                    continue
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                if is_dir and name.casefold() in _SKIP_DIRS:
                    continue
                if is_dir:
                    queue.append(entry.path)
                if is_dir != (kind == "folder"):
                    continue
                if extensions and os.path.splitext(name)[1].lower() not in extensions:
                    continue
                if all(word in name.casefold() for word in words):
                    matches.setdefault(os.path.normcase(entry.path), entry)

    results = []
    for entry in matches.values():
        try:
            stat = entry.stat()
        except OSError:
            continue
        results.append(
            {
                "path": entry.path,
                "name": entry.name,
                "folder": os.path.dirname(entry.path),
                "modified": datetime.datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                ),
                "_mtime": stat.st_mtime,
            }
        )
    # Documents before everything else (source code, logs...), then newest first
    documents = set().union(*FILE_KINDS.values(), {".txt", ".md"})
    results.sort(
        key=lambda r: (
            os.path.splitext(r["name"])[1].lower() in documents,
            r["_mtime"],
        ),
        reverse=True,
    )
    for result in results:
        del result["_mtime"]
    return {
        "matches": results[:limit],
        "total_found": len(results),
        # False: the search ran out of time before covering every folder
        "searched_everywhere": complete,
    }


def _user32():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    return user32


def _is_cloaked(hwnd: int) -> bool:
    """Hidden UWP/background windows report as visible but are cloaked by DWM."""
    import ctypes
    from ctypes import wintypes

    cloaked = wintypes.DWORD()
    result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd), 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
    )
    return result == 0 and bool(cloaked.value)


def list_windows() -> list[dict]:
    """Visible top-level windows with a title, front-most first."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    user32 = _user32()
    windows: list[dict] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def collect(hwnd: int, _: int) -> bool:
        if not user32.IsWindowVisible(hwnd) or _is_cloaked(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            windows.append({"id": int(hwnd), "title": buffer.value})
        return True

    user32.EnumWindows(collect, 0)
    return windows


def focus_window_with_title(title: str, *, timeout_seconds: float = 2.0) -> bool:
    """Bring the first window whose title contains ``title`` to the front."""
    if sys.platform != "win32":
        return False

    def find_window() -> int | None:
        return next((w["id"] for w in list_windows() if title in w["title"]), None)

    deadline = time.monotonic() + timeout_seconds
    hwnd = find_window()
    while hwnd is None and time.monotonic() < deadline:
        time.sleep(0.05)
        hwnd = find_window()
    return hwnd is not None and focus_window_handle(hwnd)


_BROWSER_TABS_SCRIPT = Path(__file__).with_name("browser_tabs.ps1")


def browser_tabs(select: str = "") -> dict:
    """Every open browser window (Chrome, Edge, Firefox, Brave, Opera) and its tabs,
    read through Windows UI Automation in about a second. With ``select``, the first
    tab whose name contains it is made the active tab: {"windows": [...],
    "selected": {"browser", "window", "tab"} or None}."""
    if sys.platform != "win32":
        return {"windows": [], "selected": None}
    command = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(_BROWSER_TABS_SCRIPT),
    ]
    if select:
        command += ["-Select", select]
    done = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if done.returncode != 0:
        raise DesktopError(
            f"Could not read the browser tabs: {done.stderr.strip()[:200]}"
        )
    data = json.loads(done.stdout or "{}")
    windows = data.get("windows") or []
    if isinstance(windows, dict):  # PowerShell writes a list of one as an object
        windows = [windows]
    for window in windows:
        tabs = window.get("tabs") or []
        window["tabs"] = [tabs] if isinstance(tabs, str) else tabs
    return {"windows": windows, "selected": data.get("selected")}


_BROWSER_ITEM_SCRIPT = Path(__file__).with_name("browser_item.ps1")


def browser_item(text: str) -> dict:
    """A list row on screen in a browser window, such as an email in the Gmail inbox,
    found by part of its text ("unread" for the topmost unread email): {"found",
    "item": {"name", "window", "x", "y"}} in screen pixels, or "already_open" when a
    browser window already shows it."""
    if sys.platform != "win32":
        return {"found": False, "item": None}
    done = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_BROWSER_ITEM_SCRIPT),
            "-Text",
            text,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if done.returncode != 0:
        raise DesktopError(f"Could not read the browser: {done.stderr.strip()[:200]}")
    return json.loads(done.stdout or "{}")


_BROWSER_TEXT_SCRIPT = Path(__file__).with_name("browser_text.ps1")


def browser_text(text: str = "", window: int = 0) -> dict:
    """The exact text of the page in a browser window (the one whose title contains
    ``text``, else the front one), in reading order: {"found", "title", "text",
    "truncated"}. Numbers come out exactly, unlike reading a screenshot."""
    if sys.platform != "win32":
        return {"found": False}
    command = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(_BROWSER_TEXT_SCRIPT),
    ]
    if window:
        command += ["-Window", str(window)]
    elif text:
        command += ["-Text", text]
    done = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if done.returncode != 0:
        raise DesktopError(f"Could not read the page: {done.stderr.strip()[:200]}")
    return json.loads(done.stdout or "{}")


async def settled_browser_text(
    text: str = "", *, window: int = 0, wait: float = 8.0
) -> dict:
    """browser_text, read again each second until the page stops changing: the
    browser makes a freshly opened page's text readable only after a few seconds
    (an email showed just its sender at first, its body 3-5 s later)."""
    deadline = time.monotonic() + wait
    page = await asyncio.to_thread(browser_text, text, window)
    while time.monotonic() < deadline:
        await asyncio.sleep(1.0)
        again = await asyncio.to_thread(browser_text, text, window)
        if (
            again.get("found")
            and again.get("text") == page.get("text")
            and len(again.get("text", "")) > 200
        ):
            return again
        page = again if again.get("found") else page
    return page


def focus_window_handle(hwnd: int) -> bool:
    """Bring a window to the front by its handle."""
    if sys.platform != "win32":
        return False

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    user32.IsIconic.argtypes = [wintypes.HWND]

    # Windows only lets the foreground thread hand over focus: borrow its input queue
    foreground = user32.GetForegroundWindow()
    current_thread = kernel32.GetCurrentThreadId()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
    attached = bool(
        foreground_thread
        and foreground_thread != current_thread
        and user32.AttachThreadInput(current_thread, foreground_thread, True)
    )
    try:
        # Un-minimise if needed; a maximised window stays maximised
        user32.ShowWindow(hwnd, 9 if user32.IsIconic(hwnd) else 5)  # RESTORE / SHOW
        user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040
        )  # NOSIZE|NOMOVE|SHOW
        if user32.SetForegroundWindow(hwnd) and user32.GetForegroundWindow() == hwnd:
            return True
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, foreground_thread, False)

    # Windows refused (another app has the focus): a tap of Alt counts as user
    # input, after which a window may be brought forward
    user32.keybd_event(0x12, 0, 0, 0)  # Alt down
    user32.keybd_event(0x12, 0, 2, 0)  # Alt up
    if user32.SetForegroundWindow(hwnd) and user32.GetForegroundWindow() == hwnd:
        return True
    # Still refused: at least put it on top of the other windows, where it is seen
    no_move = 0x0001 | 0x0002 | 0x0010 | 0x0040  # NOSIZE|NOMOVE|NOACTIVATE|SHOW
    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, no_move)  # HWND_TOPMOST
    user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, no_move)  # HWND_NOTOPMOST
    return False


def _draw_pointer(image: Image.Image, x: int, y: int) -> None:
    # Screenshots exclude the cursor, but viewers (and the model) should see it
    draw = ImageDraw.Draw(image)
    arrow = [
        (x, y),
        (x, y + 18),
        (x + 5, y + 14),
        (x + 9, y + 22),
        (x + 12, y + 21),
        (x + 8, y + 13),
        (x + 14, y + 13),
    ]
    draw.polygon(arrow, fill="white", outline="black")


class LocalDesktop:
    """Mouse, keyboard, windows and screenshots for the gatekeeper."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stopped_until = 0.0
        self._size: tuple[int, int] | None = None
        if sys.platform == "win32":
            import ctypes

            # Physical pixels everywhere, so screenshots and mouse coordinates agree
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except OSError:
                ctypes.windll.user32.SetProcessDPIAware()

    async def act(self, op: str, **params) -> dict:
        return await asyncio.to_thread(self._act, op, params)

    async def screenshot(self, **params) -> bytes:
        """PNG by default; format="jpeg", quality=, width= for a smaller frame."""
        return await asyncio.to_thread(self._screenshot, params)

    async def size(self) -> tuple[int, int]:
        if self._size is None:
            result = await self.act("size")
            self._size = (int(result["width"]), int(result["height"]))
        return self._size

    async def to_pixels(self, x: float, y: float) -> tuple[int, int]:
        """Convert 0-1000 normalized screen coordinates (what the model uses) to pixels."""
        width, height = await self.size()
        px = round(min(max(float(x), 0), 1000) / 1000 * (width - 1))
        py = round(min(max(float(y), 0), 1000) / 1000 * (height - 1))
        # Stay 1px off the edges: an exact corner is the user's emergency stop
        return min(max(px, 1), width - 2), min(max(py, 1), height - 2)

    async def has_window(self, title_part: str) -> bool:
        windows = (await self.act("windows"))["windows"]
        return any(title_part.casefold() in w["title"].casefold() for w in windows)

    async def find_browser_tab(self, text: str) -> dict:
        """Look through every tab of every open browser for ``text`` (e.g. "Gmail");
        switch to the first match and bring its window to the front."""
        self._check_stopped()
        if not text.strip():
            raise DesktopError("Say what to look for in the tab names, e.g. Gmail.")
        tabs = await asyncio.to_thread(browser_tabs, text.strip())
        matches = [
            {"browser": w["browser"], "tab": tab}
            for w in tabs["windows"]
            for tab in w["tabs"]
            if text.strip().casefold() in tab.casefold()
        ]
        selected = tabs["selected"]
        if selected:
            await asyncio.to_thread(focus_window_handle, int(selected["window"]))
            await asyncio.sleep(
                0.4
            )  # the tab's page is drawn before the next screenshot
        return {
            "found": bool(selected),
            "showing": {"browser": selected["browser"], "tab": selected["tab"]}
            if selected
            else None,
            "matching_tabs": matches,
            "browser_windows_checked": len(tabs["windows"]),
        }

    async def open_browser_item(self, text: str) -> dict:
        """Double-click a list row in a browser window (e.g. an email in the Gmail
        inbox) found by its text, with the real mouse so the user sees it."""
        self._check_stopped()
        if not text.strip():
            raise DesktopError('Say which item to open: words from it, or "unread".')
        found = await asyncio.to_thread(browser_item, text.strip())
        if found.get("already_open"):
            window = found["already_open"]
            await asyncio.to_thread(focus_window_handle, int(window["window"]))
            page = await settled_browser_text(text.strip())
            return {
                "opened": False,
                "already_open": window["title"],
                "page_text": page.get("text", ""),
            }
        item = found.get("item")
        if not found.get("found") or not item:
            return {
                "opened": False,
                "reason": f"No row matching {text!r} is visible in the browser. Scroll "
                "or go back to the list first.",
            }
        await asyncio.to_thread(focus_window_handle, int(item["window"]))
        await asyncio.sleep(0.2)
        await self.act("click", x=int(item["x"]), y=int(item["y"]), clicks=2)
        await asyncio.sleep(1.5)  # the email opens before it is read
        # Its exact text (front window: the one just clicked)
        page = await settled_browser_text(window=int(item["window"]))
        return {"opened": True, "item": item["name"], "page_text": page.get("text", "")}

    async def read_browser_window(self, text: str = "") -> dict:
        """The exact text of the page in a browser window (see browser_text)."""
        self._check_stopped()
        page = await settled_browser_text(text.strip())
        if not page.get("found") and text.strip():
            # Open in a tab that is not showing: switch to it, then read it
            tabs = await asyncio.to_thread(browser_tabs, text.strip())
            if tabs["selected"]:
                await asyncio.to_thread(
                    focus_window_handle, int(tabs["selected"]["window"])
                )
                await asyncio.sleep(0.8)
                page = await settled_browser_text(text.strip())
        if not page.get("found"):
            return {"found": False, "reason": "No browser window like that is open."}
        return page

    async def find_files(self, query: str, kind: str = "any") -> dict:
        return await asyncio.to_thread(find_files, query, search_roots(), kind=kind)

    async def open_file(self, path: str) -> dict:
        """Open a file in its usual app, or a folder in File Explorer."""
        self._check_stopped()
        target = Path(path)
        if not target.exists():
            raise DesktopError(
                f"{path!r} does not exist. Use find_files to get the exact path."
            )
        if sys.platform != "win32":
            raise DesktopError("Opening files is only supported on Windows.")
        os.startfile(target)  # the app registered for this file type
        await asyncio.sleep(
            1.5
        )  # let the app's window appear before the next screenshot
        return {"opened": str(target)}

    async def close(self) -> None:
        return None

    # --- Blocking implementation (runs in a worker thread) -------------------------

    def _check_stopped(self) -> None:
        remaining = self._stopped_until - time.monotonic()
        if remaining > 0:
            raise DesktopError(
                "Emergency stop is active: the user moved the mouse into a screen corner. "
                f"Do nothing on the computer for {round(remaining)} more seconds and ask "
                "the user how to proceed."
            )

    def _act(self, op: str, params: dict) -> dict:
        import pyautogui

        if op == "size":
            width, height = pyautogui.size()
            return {"width": width, "height": height}
        if op == "windows":
            return {"windows": list_windows()}

        self._check_stopped()
        with self._lock:
            try:
                result = self._run(pyautogui, op, params)
            except pyautogui.FailSafeException as exc:
                self._stopped_until = time.monotonic() + EMERGENCY_STOP_SECONDS
                raise DesktopError(
                    "Emergency stop: the user moved the mouse into a screen corner. Stop "
                    "and ask the user before doing anything else on the computer."
                ) from exc
        px, py = pyautogui.position()
        return {"ok": True, "cursor": {"x": px, "y": py}, **(result or {})}

    def _run(self, pyautogui, op: str, p: dict) -> dict | None:
        if op == "move":
            pyautogui.moveTo(p["x"], p["y"], duration=0.2)
        elif op == "click":
            pyautogui.click(
                p["x"],
                p["y"],
                clicks=int(p.get("clicks", 1)),
                interval=0.1,
                button=p.get("button", "left"),
                duration=0.2,
            )
        elif op == "drag":
            pyautogui.moveTo(p["x"], p["y"], duration=0.2)
            pyautogui.dragTo(p["to_x"], p["to_y"], duration=0.5, button="left")
        elif op == "scroll":
            # pyautogui counts raw wheel units; one notch is 120
            pyautogui.scroll(int(p.get("amount", 0)) * 120, x=p.get("x"), y=p.get("y"))
        elif op == "type":
            self._type(pyautogui, str(p.get("text", "")))
        elif op == "press":
            pyautogui.press(self._key(pyautogui, p["key"]))
        elif op == "hotkey":
            pyautogui.hotkey(*[self._key(pyautogui, k) for k in p["keys"]])
        elif op in ("focus_window", "close_window"):
            title = str(p.get("title", ""))
            window = next(
                (
                    w
                    for w in list_windows()
                    if title.casefold() in w["title"].casefold()
                ),
                None,
            )
            if not title or window is None:
                raise DesktopError(f"No open window matches {title!r}.")
            if op == "focus_window":
                focus_window_with_title(window["title"])
            else:
                _user32().PostMessageW(
                    window["id"], 0x0010, 0, 0
                )  # WM_CLOSE: app may ask to save
            return {"window": window["title"]}
        elif op == "open_app":
            app = p.get("app")
            if app not in APPS:
                raise DesktopError(f"Unknown app {app!r}; choose from {sorted(APPS)}")
            subprocess.Popen(
                ["cmd", "/c", "start", "", APPS[app]],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return {"opened": app}
        else:
            raise DesktopError(f"Unknown op {op!r}")
        return None

    @staticmethod
    def _key(pyautogui, name: str) -> str:
        key = _KEY_ALIASES.get(name.strip().lower(), name.strip().lower())
        if key not in pyautogui.KEYBOARD_KEYS:
            raise DesktopError(f"Unknown key {name!r}.")
        return key

    @staticmethod
    def _type(pyautogui, text: str) -> None:
        if text.isascii():
            pyautogui.write(text, interval=0.02)
            return
        # pyautogui only types ASCII: paste anything else, then restore the clipboard
        import pyperclip

        previous = pyperclip.paste()
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        pyperclip.copy(previous)

    def _screenshot(self, params: dict) -> bytes:
        import pyautogui
        from PIL import ImageGrab

        try:
            image = ImageGrab.grab()  # primary monitor
        except OSError as exc:
            raise DesktopError(f"Could not capture the screen: {exc}") from exc
        _draw_pointer(image, *pyautogui.position())
        width = int(params.get("width", 0))
        if 0 < width < image.width:
            image = image.resize((width, round(image.height * width / image.width)))
        buffer = io.BytesIO()
        if params.get("format") == "jpeg":
            image.convert("RGB").save(
                buffer, format="JPEG", quality=int(params.get("quality", 70))
            )
        else:
            image.save(buffer, format="PNG")
        return buffer.getvalue()
