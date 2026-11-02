"""Stream the computer's screen into the LiveKit room as a screen-share video track.

Lets the web app on a phone (possibly on mobile data) watch what the agent does
on the PC through the same LiveKit connection as the call. Runs only while a
client asks for it, to save CPU.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging

from livekit import rtc
from PIL import Image

logger = logging.getLogger("jarvis.screen_stream")

TRACK_NAME = "pc-screen"


class ScreenStreamer:
    def __init__(self, backend, room, *, fps: float = 4, width: int = 1280) -> None:
        self._backend = backend
        self._room = room
        self._interval = 1 / fps
        self._fps = fps
        self._width = width
        self._source: rtc.VideoSource | None = None
        self._publication = None
        self._task: asyncio.Task | None = None
        self.frames_sent = 0

    @property
    def active(self) -> bool:
        return self._task is not None

    async def _frame(self) -> rtc.VideoFrame | None:
        jpeg = await self._backend.screenshot(format="jpeg", quality=70, width=self._width)
        if not jpeg:
            return None
        image = Image.open(io.BytesIO(jpeg)).convert("RGBA")
        return rtc.VideoFrame(image.width, image.height, rtc.VideoBufferType.RGBA, image.tobytes())

    async def start(self) -> bool:
        """Publish the track and start sending frames. False if no screen is available."""
        if self.active:
            return True
        first = await self._frame()
        if first is None:
            return False
        self._source = rtc.VideoSource(first.width, first.height)
        track = rtc.LocalVideoTrack.create_video_track(TRACK_NAME, self._source)
        options = rtc.TrackPublishOptions(
            source=rtc.TrackSource.SOURCE_SCREENSHARE,
            simulcast=False,
            video_encoding=rtc.VideoEncoding(max_framerate=self._fps, max_bitrate=1_500_000),
        )
        self._publication = await self._room.local_participant.publish_track(track, options)
        self._source.capture_frame(first)
        self.frames_sent = 1
        self._task = asyncio.create_task(self._run())
        logger.info("screen stream started")
        return True

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            started = loop.time()
            try:
                frame = await self._frame()
                if frame is not None and self._source is not None:
                    self._source.capture_frame(frame)
                    self.frames_sent += 1
            except Exception:
                logger.exception("screen frame failed")
            await asyncio.sleep(max(0.0, self._interval - (loop.time() - started)))

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._publication is not None:
            with contextlib.suppress(Exception):
                await self._room.local_participant.unpublish_track(self._publication.sid)
            self._publication = None
        self._source = None
        logger.info("screen stream stopped")
