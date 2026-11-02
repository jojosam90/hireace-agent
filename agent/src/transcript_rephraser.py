"""Show the user's words as they meant them, not as speech recognition heard them.

Speech recognition sometimes mishears words ("oven the sand box"), writes them
in the wrong script ("계 오픈 엑셀 폼" for "open Excel"), and keeps every "um",
stutter and false start. After each utterance a fast text model rewrites the raw
transcript into the clean sentence the user meant, using the recent
conversation as context. The raw words are never shown: the user's bubble shows
"…" while they speak and until the clean sentence is ready (web and mobile app
alike).

How it plugs in: this listener runs before RoomIO's (registered before
session.start). It turns the final transcript into an interim "…", so the room
keeps the segment open, then emits a final event with the clean text, which
RoomIO publishes into the same segment.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import Awaitable, Callable

from livekit.agents import UserInputTranscribedEvent

from transcript_guard import UNCLEAR, clean_user_transcript, drop_fillers

logger = logging.getLogger("jarvis.rephraser")

PLACEHOLDER = "…"
UNCLEAR_MARKER = "<UNCLEAR>"
TIMEOUT_SECONDS = 4.0
CAREFUL_TIMEOUT_SECONDS = 5.0

Rephrase = Callable[[str, str], Awaitable[str]]

_LANGUAGE_NAMES = {"en": "English", "zh": "Simplified Chinese (普通话)"}

_INSTRUCTIONS = """You turn speech-recognition transcripts into clean text for a voice assistant called HireAce.
The user spoke {language}. The raw transcript may contain misheard words, missing
punctuation, filler words, stutters, false starts, repeated words, or {language}
words written phonetically in another script.

Reply with ONLY the user's own words, cleaned up, in {language} with correct
spelling and punctuation:
- Drop filler words and sounds (um, uh, er, hmm, like, you know, 嗯, 呃, 那个, 就是).
- Drop stutters, repeated words and abandoned starts ("open the, the, uh, can you
  open Excel" -> "Can you open Excel?").
- Keep everything else exactly as said: the same words, the same kind of sentence
  (an answer stays an answer, a statement stays a statement, a question stays a
  question) and every no, not, don't, yes, only or never. "No, the folder called
  Acme." stays "No, the folder called Acme." Never turn it into a command.
- Fix only words that were clearly misheard, using the conversation for context.
  Do not answer it, add information or make it more polite than they were.
- If the words are clearly in another language, write their meaning in {language}.
- Keep names, websites, file names and English product names as spoken (for
  example YouTube, trip.com, Acme).
Only if the transcript is meaningless gibberish, reply exactly: <UNCLEAR>

What users typically say to HireAce: open websites (trip.com, YouTube, Google,
Wikipedia), search the web, ask the weather, open Word, Excel (表格), PowerPoint or
Outlook, find or open a file or folder, open or close the browser or a tab, click
or type things, end the call (结束通话), or call it by name (HireAce). Prefer these
meanings when the raw words sound like them.

Examples:
- "um so can you uh find the the acme pro proposal" -> "Can you find the Acme proposal?"
- "계 오픈 엑셀 폼" -> "Can you open Excel, please?"
- "enkor" or "and call" after the user says goodbye -> "End call."
- "go to treat.com and find flights" -> "Go to trip.com and find flights."
- "no uh the the folder called acme" -> "No, the folder called Acme."
- "yeah the desktop one" -> "Yeah, the desktop one."
- "嗯 可 以 帮 我 那个 打 开 表 格" -> "可以帮我打开表格吗？"
- "结 对 话" -> "结束对话。\""""  # noqa: RUF001 (Chinese punctuation is the point)


def openai_rephraser(language: str) -> Rephrase:
    """Rephrase with a fast OpenAI text model (uses OPENAI_API_KEY), typically in
    about a second."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    instructions = _INSTRUCTIONS.format(
        language=_LANGUAGE_NAMES.get(language, "English")
    )
    model = os.environ.get("OPENAI_REPHRASE_MODEL", "gpt-4.1-mini")

    async def rephrase(raw: str, context: str) -> str:
        response = await client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=120,
            messages=[
                {"role": "system", "content": instructions},
                {
                    "role": "user",
                    "content": f"Recent conversation:\n{context or '(none)'}\n\nRaw transcript: {raw}",
                },
            ],
        )
        return (response.choices[0].message.content or "").strip()

    return rephrase


class TranscriptRephraser:
    def __init__(
        self,
        session,
        language: str,
        *,
        rephrase: Rephrase | None = None,
        careful: Callable[[float], Awaitable[str | None]] | None = None,
        reply: Callable[[str], object] | None = None,
    ) -> None:
        self._session = session
        self._language = language
        self._rephrase = rephrase or openai_rephraser(language)
        # A second, careful transcription of the user's audio (careful_transcriber.py)
        self._careful = careful
        # Called with each turn's final, clean words: the agent answers those, not
        # its own quick (often wrong) hearing of the audio
        self._reply = reply
        self._pending: tuple[asyncio.Task, str] | None = None  # (task, fallback text)
        self._emitting = False
        # "…" bubble opened when speech stops; closed as unclear if no words follow
        self.placeholder_timeout = 12.0
        self._placeholder_timer: asyncio.TimerHandle | None = None
        # Set when the user's latest words are on screen in their final, clean form.
        # The agent's reply text waits for it, so the user's line always comes first.
        self._settled = asyncio.Event()
        self._settled.set()
        self._bubble_open = False  # a "…" bubble is showing for the current turn

    def on_user_state_changed(self, ev) -> None:
        if ev.new_state == "speaking":
            self._settled.clear()

    async def wait_user_text(self, timeout: float = 9.0) -> None:
        """Wait until the user's latest line is shown (or give up after timeout)."""
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._settled.wait(), timeout)

    # Called for every transcript event, before RoomIO publishes it
    def on_transcribed(self, ev: UserInputTranscribedEvent) -> None:
        if self._emitting:
            return  # our own corrected event: publish as is

        raw = ev.transcript
        if self._placeholder_timer is not None:
            self._placeholder_timer.cancel()
            self._placeholder_timer = None

        if not raw and not ev.is_final:
            # LiveKit sends an empty interim when the user stops talking, before
            # the words are transcribed. Show "…" so the user's bubble opens now,
            # in front of the agent's reply, instead of appearing after it.
            if self._pending is None:
                ev.transcript = PLACEHOLDER
                self._open_bubble()
                self._placeholder_timer = asyncio.get_running_loop().call_later(
                    self.placeholder_timeout, self._close_placeholder
                )
            return

        if ev.is_final and not raw.strip():
            # Final with no words (noise): close an open "…" as unclear, else nothing
            if self._bubble_open:
                ev.transcript = UNCLEAR.get(self._language, UNCLEAR["en"])
                self._bubble_open = False
            self._settled.set()
            return

        # The raw words are never shown, only "…" until the clean sentence is ready
        shown = PLACEHOLDER

        if self._pending is not None and not ev.is_final:
            # The user is speaking again: close the previous line now so the two
            # utterances don't merge into one bubble.
            task, fallback = self._pending
            task.cancel()
            self._pending = None
            self._emit_final(fallback)

        if not ev.is_final:
            ev.transcript = shown
            self._open_bubble()
            return

        # Final: keep the segment open (still "…") and correct it async
        ev.transcript = shown
        ev.is_final = False
        self._open_bubble()
        if self._pending is not None:  # an older correction still running
            task, fallback = self._pending
            task.cancel()
            self._pending = None
        fallback = clean_user_transcript(raw, self._language)
        task = asyncio.create_task(self._correct(raw, fallback))
        self._pending = (task, fallback)

    async def _correct(self, raw: str, fallback: str) -> None:
        if self._careful is not None:
            heard = await self._careful(CAREFUL_TIMEOUT_SECONDS)
            if heard is not None and not heard.strip():
                # The careful listen heard no words: it was background noise, not
                # the user. Stop the reply the agent started to it, and empty the
                # bubble (the app hides empty messages).
                logger.info("careful transcript is empty: noise, dropping %r", raw)
                with contextlib.suppress(Exception):
                    self._session.interrupt()
                self._pending = None
                self._emit_final("")
                return
            if heard:
                logger.info("careful transcript replaces %r with %r", raw, heard)
                cleaned = clean_user_transcript(heard, self._language)
                if drop_fillers(heard) == heard.strip():
                    # Already clean (the careful listen knows the names and drops
                    # most fillers): show it now, without a second model call, so
                    # the agent's reply is held back as briefly as possible
                    self._pending = None
                    self._emit_final(cleaned)
                    self._answer(cleaned)
                    return
                raw, fallback = heard, cleaned
        try:
            corrected = await asyncio.wait_for(
                self._rephrase(raw, self.context()), timeout=TIMEOUT_SECONDS
            )
            text = self._accept(raw, corrected, fallback)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "transcript rephrase failed (%s); showing tidied raw text", exc
            )
            text = fallback
        if text != raw:
            logger.info("transcript rephrased: %r -> %r", raw, text)
        self._pending = None
        self._emit_final(text)
        self._answer(text)

    def _answer(self, text: str) -> None:
        if self._reply is None or not text.strip():
            return
        try:
            self._reply(text)
        except Exception:
            logger.exception("could not start the reply to %r", text)

    def _accept(self, raw: str, corrected: str, fallback: str) -> str:
        if not corrected:
            return fallback
        if corrected.strip() == UNCLEAR_MARKER:
            return UNCLEAR.get(self._language, UNCLEAR["en"])
        # A model that answers instead of rephrasing produces much longer text
        if len(corrected) > 2 * len(raw) + 40:
            return fallback
        return clean_user_transcript(corrected, self._language)

    def context(self, turns: int = 6) -> str:
        history = getattr(self._session, "history", None)
        if history is None:
            return ""
        lines = []
        for item in history.items[-turns:]:
            text = getattr(item, "text_content", None)
            role = getattr(item, "role", None)
            if text and role in ("user", "assistant"):
                lines.append(f"{'User' if role == 'user' else 'HireAce'}: {text}")
        return "\n".join(lines)

    def _close_placeholder(self) -> None:
        self._placeholder_timer = None
        self._emit_final(UNCLEAR.get(self._language, UNCLEAR["en"]))

    def _open_bubble(self) -> None:
        self._bubble_open = True
        self._settled.clear()

    def _emit_final(self, text: str) -> None:
        self._emitting = True
        try:
            self._session.emit(
                "user_input_transcribed",
                UserInputTranscribedEvent(transcript=text, is_final=True),
            )
        finally:
            self._emitting = False
            self._bubble_open = False
            self._settled.set()

    async def wait_idle(self) -> None:
        """Wait for any running correction (tests, shutdown)."""
        while self._pending is not None:
            task = self._pending[0]
            try:
                await task
            except asyncio.CancelledError:
                if self._pending and self._pending[0] is task:
                    self._pending = None
