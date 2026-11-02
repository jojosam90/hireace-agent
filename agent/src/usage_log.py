"""Token counts for the admin portal, and whether the portal's usage limit was reached.

Each answer from the voice model adds a line to <data folder>/usage.jsonl; the monitor
(fleet.ps1) sends the counts with its next check-in and clears them. Only counts: never what
was said. The limit is a file the monitor writes when the portal says so.
"""

from __future__ import annotations

import datetime
import json
import logging
import os

from livekit.agents.metrics import RealtimeModelMetrics

from settings import data_dir

logger = logging.getLogger("agent")

LIMIT_MESSAGE = (
    "Tell the user, in one short sentence in their language, that this PC has reached its "
    "monthly usage limit and that they should ask their administrator. Say nothing else."
)


def record(metrics: object) -> None:
    """Never lets a problem here disturb the call."""
    if not isinstance(metrics, RealtimeModelMetrics):
        return
    try:
        given = metrics.input_token_details
        cached = given.cached_tokens_details
        made = metrics.output_token_details
        line = {
            "day": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
            "model": os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1"),
            "inText": given.text_tokens,
            "inAudio": given.audio_tokens,
            "inImage": given.image_tokens,
            "cachedText": cached.text_tokens if cached else 0,
            "cachedAudio": cached.audio_tokens if cached else 0,
            "outText": made.text_tokens,
            "outAudio": made.audio_tokens,
        }
        folder = data_dir()
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / "usage.jsonl", "a", encoding="utf-8") as file:
            file.write(json.dumps(line) + "\n")
    except Exception:
        logger.exception("could not record usage")


def limit_reached() -> bool:
    return (data_dir() / "usage-limit").exists()
