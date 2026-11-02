"""A second agent with its own eyes: reads the screen in parallel with the voice agent.

The voice agent keeps talking while the helper works:
- ask(): the agent asks a question about the screen ("is the file open?", "where is
  the Save button?"); the answer arrives as a note a moment later, or the agent can
  wait for it when it needs the answer to continue.
- watch: after the agent acts on the desktop or in Office, the helper checks the
  screen for anything in the way (dialogs, errors, sign-in pages, the Enable
  Editing bar, "save changes?" prompts) and speaks up only when something needs
  attention.

It uses a fast vision model on a 1600px screenshot from the gatekeeper (read-only).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os

logger = logging.getLogger("jarvis.screen_helper")

# Actions after which the helper checks the screen for anything in the way
WATCHED_ACTIONS = {
    "screen_click",
    "screen_drag",
    "screen_type",
    "screen_key",
    "open_app",
    "open_file",
    "focus_window",
    "close_window",
    "office_save",
}
WATCH_DELAY_SECONDS = 1.5  # let the screen settle; a newer action restarts the wait

_SYSTEM = """You are the eyes of HireAce, a voice assistant that controls this Windows PC.
You see a screenshot of the whole screen. Answer precisely and briefly (under 80
words, plain text). Name the window or app in front and quote exact visible text
when it matters. Mention anything blocking: dialogs, error messages, sign-in
pages, permission prompts, the yellow "Enable Editing" / Protected View bar,
"save changes?" prompts, loading spinners, an app not responding.
When asked where something is, give its centre as (x, y) on a 0-1000 scale
across the screen ((0, 0) top-left, (1000, 1000) bottom-right).
Ignore the small floating HireAce panel (the user's chat with the agent)."""

_WATCH_QUESTION = (
    "Is anything on screen blocking work or needing the user's attention right now "
    "(a dialog, error, sign-in page, permission prompt, Enable Editing bar, save "
    "prompt, app not responding)? If nothing needs attention reply exactly: OK. "
    "Otherwise describe it in one sentence."
)


class ScreenHelper:
    def __init__(self, backend, *, model: str | None = None) -> None:
        self._backend = backend
        self._model = model or os.environ.get("SCREEN_HELPER_MODEL", "gpt-4.1-mini")
        self._client = None
        self._watch: asyncio.Task | None = None
        self._last_alert = ""
        self._tasks: set[asyncio.Task] = set()

    async def look(self, question: str) -> str:
        """Answer a question about what is on screen now."""
        jpeg = await self._backend.screenshot(format="jpeg", quality=80, width=1600)
        if not jpeg:
            return "The screen is not available."
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI()
        image = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
        response = await self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            max_tokens=250,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {"url": image, "detail": "high"},
                        },
                    ],
                },
            ],
        )
        return (response.choices[0].message.content or "").strip()

    def ask_in_background(self, session, question: str) -> None:
        """Look while the agent keeps talking; the answer is handed to it when ready."""

        async def run() -> None:
            try:
                answer = await self.look(question)
            except Exception as exc:
                logger.warning("screen helper failed: %s", exc)
                answer = f"The screen helper could not look: {exc}"
            logger.info("screen helper answered %r: %r", question, answer)
            session.generate_reply(
                instructions=(
                    f"Your screen helper answered your question {question!r}: {answer} "
                    "Use it to continue the task; tell the user only what matters, briefly."
                )
            )

        self._spawn(run())

    def after_action(self, session, action: str) -> None:
        """Check the screen for anything in the way once it settles after an action."""
        if action not in WATCHED_ACTIONS:
            return
        if self._watch is not None and not self._watch.done():
            self._watch.cancel()  # a newer action: check after that one instead
        self._watch = self._spawn(self._check(session))

    async def _check(self, session) -> None:
        await asyncio.sleep(WATCH_DELAY_SECONDS)
        try:
            alert = await self.look(_WATCH_QUESTION)
        except Exception as exc:
            logger.warning("screen watch failed: %s", exc)
            return
        if alert.rstrip(".").upper() == "OK" or alert == self._last_alert:
            return
        self._last_alert = alert
        logger.info("screen helper noticed: %s", alert)
        session.generate_reply(
            instructions=(
                f"Your screen helper noticed on the screen: {alert} If it blocks the task, "
                "deal with it (for an Office Enable Editing bar, the office tools handle it); "
                "otherwise mention it to the user in one short sentence."
            )
        )

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def aclose(self) -> None:
        for task in list(self._tasks):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
