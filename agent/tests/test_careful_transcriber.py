import asyncio
import time

import careful_transcriber
from careful_transcriber import SAMPLE_RATE, CarefulTranscriber


class _State:
    def __init__(self, old, new):
        self.old_state, self.new_state = old, new


def _frames(transcriber, seconds_ago_start, seconds_ago_end, *, step=0.1):
    """10 ms-ish chunks of silence with arrival times in the past."""
    now = time.monotonic()
    t = now - seconds_ago_start
    while t <= now - seconds_ago_end:
        transcriber._frames.append((t, b"\x00\x00" * int(SAMPLE_RATE * step)))
        t += step


async def test_the_turns_own_audio_is_transcribed_with_context(monkeypatch):
    monkeypatch.setattr(careful_transcriber, "TAIL_SECONDS", 0)
    sent = {}

    async def request(wav):
        sent["wav_bytes"] = len(wav)
        return "No, the folder called Acme."

    transcriber = CarefulTranscriber("en", vocabulary=["Acme"], context=lambda: "")
    transcriber._request = request
    _frames(transcriber, 30, 10)  # older audio, before this turn: not sent
    transcriber.on_user_state_changed(_State("listening", "speaking"))
    _frames(transcriber, 0, 0)
    await asyncio.sleep(0.6)
    _frames(transcriber, 0.5, 0)
    transcriber.on_user_state_changed(_State("speaking", "listening"))

    assert await transcriber.latest(timeout=2) == "No, the folder called Acme."
    # about 0.6 s of speech plus the lead-in, never the 20 s of older audio
    assert sent["wav_bytes"] < 3 * SAMPLE_RATE * 2


async def test_no_turn_means_no_careful_transcript():
    transcriber = CarefulTranscriber("en", vocabulary=[], context=lambda: "")
    assert await transcriber.latest(timeout=0.1) is None  # no turn: nothing to offer
