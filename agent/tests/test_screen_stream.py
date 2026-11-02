import asyncio
import io

from PIL import Image

from screen_stream import TRACK_NAME, ScreenStreamer


def _jpeg(width: int = 320, height: int = 200) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "navy").save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeBackend:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    async def screenshot(self, **params):
        self.requests.append(params)
        return _jpeg()


class FakePublication:
    sid = "TR_screen"


class FakeParticipant:
    def __init__(self) -> None:
        self.published = []
        self.unpublished = []

    async def publish_track(self, track, options):
        self.published.append((track.name, options))
        return FakePublication()

    async def unpublish_track(self, sid):
        self.unpublished.append(sid)


class FakeRoom:
    def __init__(self) -> None:
        self.local_participant = FakeParticipant()


async def test_streams_screen_frames_while_on_and_unpublishes_when_off():
    backend, room = FakeBackend(), FakeRoom()
    streamer = ScreenStreamer(backend, room, fps=20)

    await streamer.start()
    await asyncio.sleep(0.3)
    await streamer.stop()

    assert room.local_participant.published[0][0] == TRACK_NAME
    assert streamer.frames_sent >= 3
    assert backend.requests[0]["format"] == "jpeg"
    assert room.local_participant.unpublished == ["TR_screen"]
    assert not streamer.active


async def test_start_twice_publishes_once():
    room = FakeRoom()
    streamer = ScreenStreamer(FakeBackend(), room, fps=20)

    await streamer.start()
    await streamer.start()
    await streamer.stop()

    assert len(room.local_participant.published) == 1


async def test_no_screen_means_nothing_is_published():
    class NoScreen(FakeBackend):
        async def screenshot(self, **params):
            return None

    room = FakeRoom()
    streamer = ScreenStreamer(NoScreen(), room)

    assert await streamer.start() is False
    assert room.local_participant.published == []
