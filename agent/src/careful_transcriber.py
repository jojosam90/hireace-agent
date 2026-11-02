"""A second, careful listen to each thing the user says.

The realtime model's built-in transcription is quick but often mishears accented
speech (it once turned an English request into "Kendi mitik ... foder Acme pet testol"). This keeps the
last minute of the user's microphone audio and, when they stop talking, sends
exactly that turn to a dedicated transcription model with context: the names
they use and what the agent just said. That transcript replaces the quick one in the
user's chat bubble.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import os
import time
import wave
from collections import deque
from collections.abc import Callable

from livekit import rtc

logger = logging.getLogger("jarvis.careful")

SAMPLE_RATE = 16_000
KEEP_SECONDS = 60
# The speech-start/stop events lag the audio a little: pad the cut on both sides
LEAD_SECONDS = 0.8
TAIL_SECONDS = 0.3
MIN_SECONDS = 0.4

_LANGUAGES = {"en": "en", "zh": "zh"}


class CarefulTranscriber:
    def __init__(
        self,
        language: str,
        *,
        vocabulary: list[str],
        context: Callable[[], str],
        model: str | None = None,
    ) -> None:
        self._language = _LANGUAGES.get(language, "en")
        self._vocabulary = ", ".join(dict.fromkeys(vocabulary))
        self._context = context
        self._model = model or os.environ.get(
            "CAREFUL_TRANSCRIBE_MODEL", "gpt-transcribe"
        )
        self._frames: deque[tuple[float, bytes]] = deque()  # (arrival time, 16-bit PCM)
        self._speech_started: float | None = None
        self._latest: asyncio.Task | None = None
        self._reader: asyncio.Task | None = None
        self._client = None

    # --- Audio ---------------------------------------------------------------------

    def attach(self, participant: rtc.RemoteParticipant) -> None:
        """Start keeping the participant's microphone audio."""
        stream = rtc.AudioStream.from_participant(
            participant=participant,
            track_source=rtc.TrackSource.SOURCE_MICROPHONE,
            sample_rate=SAMPLE_RATE,
            num_channels=1,
        )
        self._reader = asyncio.create_task(self._read(stream))

    async def _read(self, stream: rtc.AudioStream) -> None:
        try:
            async for event in stream:
                now = time.monotonic()
                self._frames.append((now, bytes(event.frame.data)))
                while self._frames and self._frames[0][0] < now - KEEP_SECONDS:
                    self._frames.popleft()
        finally:
            await stream.aclose()

    async def aclose(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader

    # --- Turns ---------------------------------------------------------------------

    def on_user_state_changed(self, ev) -> None:
        now = time.monotonic()
        if ev.new_state == "speaking":
            self._speech_started = now
        elif ev.old_state == "speaking" and self._speech_started is not None:
            start, self._speech_started = self._speech_started - LEAD_SECONDS, None
            self._latest = asyncio.create_task(self._transcribe(start, now))

    async def latest(self, timeout: float) -> str | None:
        """The careful transcript of the user's most recent turn, if ready in time.

        "" means it listened and heard no words (noise); None means no careful
        transcript is available (too slow, failed, or no audio).
        """
        if self._latest is None:
            return None
        try:
            return await asyncio.wait_for(asyncio.shield(self._latest), timeout)
        except Exception:  # timed out or failed: keep the quick transcript
            return None

    async def _transcribe(self, start: float, end: float) -> str | None:
        await asyncio.sleep(TAIL_SECONDS)  # let the last words arrive
        pcm = b"".join(
            data for t, data in self._frames if start <= t <= end + TAIL_SECONDS
        )
        if len(pcm) < MIN_SECONDS * SAMPLE_RATE * 2:
            return ""  # too short to be words
        try:
            text = await self._request(_wav(pcm))
        except Exception:
            logger.exception("careful transcription failed")
            return None
        logger.info("careful transcript: %r", text)
        return text

    async def _request(self, wav: bytes) -> str:
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI()
        context = self._context()
        prompt = f"Names the user may say: {self._vocabulary}."
        if context:
            prompt += f" The conversation so far:\n{context}"
        result = await self._client.audio.transcriptions.create(
            model=self._model,
            file=("turn.wav", wav, "audio/wav"),
            language=self._language,
            prompt=prompt[-1500:],
        )
        return result.text.strip()


def _wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm)
    return buffer.getvalue()
