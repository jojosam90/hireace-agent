import asyncio

from livekit.agents import UserInputTranscribedEvent
from livekit.rtc import EventEmitter

from transcript_guard import UNCLEAR
from transcript_rephraser import TranscriptRephraser


class FakeSession(EventEmitter):
    """Records what the room would publish (listeners registered after ours)."""

    def __init__(self) -> None:
        super().__init__()
        self.published: list[tuple[str, bool]] = []
        self.history = None


def make(rephrase, language="en"):
    session = FakeSession()
    rephraser = TranscriptRephraser(session, language, rephrase=rephrase)
    session.on("user_input_transcribed", rephraser.on_transcribed)
    # Stand-in for RoomIO, which subscribes later
    session.on("user_input_transcribed", lambda ev: session.published.append((ev.transcript, ev.is_final)))
    return session, rephraser


def say(session, text, final=True):
    session.emit("user_input_transcribed", UserInputTranscribedEvent(transcript=text, is_final=final))


async def test_final_transcript_is_replaced_by_the_rephrased_text():
    async def rephrase(raw, context):
        return "Can you open Excel?"

    session, rephraser = make(rephrase)
    say(session, "um can you uh oven the the excel")
    await rephraser.wait_idle()

    # Never the raw mumbling: "…" while correcting, then the clean sentence
    assert session.published == [("…", False), ("Can you open Excel?", True)]


async def test_raw_words_are_never_shown_while_speaking():
    async def rephrase(raw, context):
        return "Find the Acme proposal."

    session, rephraser = make(rephrase)
    say(session, "find the", final=False)
    say(session, "find the uh acme", final=False)
    say(session, "find the uh acme proposal")
    await rephraser.wait_idle()

    assert [text for text, _ in session.published] == ["…", "…", "…", "Find the Acme proposal."]


async def test_wrong_script_is_hidden_until_corrected():
    async def rephrase(raw, context):
        return "Open Excel, please."

    session, rephraser = make(rephrase)
    say(session, "계 오픈 엑셀 폼")
    await rephraser.wait_idle()

    assert session.published == [("…", False), ("Open Excel, please.", True)]


async def test_unintelligible_speech_shows_the_notice():
    async def rephrase(raw, context):
        return "<UNCLEAR>"

    session, rephraser = make(rephrase)
    say(session, "계 폼")
    await rephraser.wait_idle()

    assert session.published[-1] == (UNCLEAR["en"], True)


async def test_slow_or_failing_rephrase_falls_back_to_the_raw_text():
    async def rephrase(raw, context):
        raise TimeoutError

    session, rephraser = make(rephrase)
    say(session, "um open uh youtube youtube")
    await rephraser.wait_idle()

    # The tidied raw text: no fillers or stutters
    assert session.published[-1] == ("Open youtube", True)


async def test_new_speech_closes_the_previous_line_first():
    gate = asyncio.Event()

    async def rephrase(raw, context):
        await gate.wait()
        return "never used"

    session, rephraser = make(rephrase)
    say(session, "first line")
    say(session, "second", final=False)  # user speaks again before correction returns

    assert session.published[:3] == [
        ("…", False),
        ("First line", True),  # previous segment closed with its tidied raw text
        ("…", False),
    ]
    gate.set()
    await rephraser.wait_idle()


async def test_runaway_answers_are_rejected():
    async def rephrase(raw, context):
        return "Sure! Here is a long answer to your question about the weather in Singapore today, " * 3

    session, rephraser = make(rephrase)
    say(session, "weather singapore")
    await rephraser.wait_idle()

    assert session.published[-1] == ("Weather singapore", True)


async def test_chinese_mode_output_is_tidied():
    async def rephrase(raw, context):
        return "可以 帮我 打开 表格 吗?"

    session, rephraser = make(rephrase, language="zh")
    say(session, "嗯 可 以 帮 我 打 开 表 格 吗")
    await rephraser.wait_idle()

    assert session.published[-1] == ("可以帮我打开表格吗？", True)


async def test_bubble_opens_in_place_when_speech_stops():
    """LiveKit sends an empty interim when the user stops talking; showing it as
    '…' puts the user's bubble before the agent's reply even if the words come later."""

    async def rephrase(raw, context):
        return "What's the weather today?"

    session, rephraser = make(rephrase)
    say(session, "", final=False)  # speech stopped, words not transcribed yet
    say(session, "whats the whether today")
    await rephraser.wait_idle()

    assert session.published == [
        ("…", False),
        ("…", False),
        ("What's the weather today?", True),
    ]


class _State:
    def __init__(self, new_state):
        self.new_state = new_state


async def test_reply_text_waits_until_the_users_line_is_shown():
    gate = asyncio.Event()

    async def rephrase(raw, context):
        await gate.wait()
        return "Open Excel."

    session, rephraser = make(rephrase)
    rephraser.on_user_state_changed(_State("speaking"))
    waiter = asyncio.create_task(rephraser.wait_user_text(timeout=5))
    say(session, "um open excel")
    await asyncio.sleep(0.05)
    assert not waiter.done()  # the agent's text is held while the user's line is "…"

    gate.set()
    await asyncio.wait_for(waiter, 1)
    assert session.published[-1] == ("Open Excel.", True)


async def test_reply_text_is_not_held_forever():
    _, rephraser = make(lambda raw, ctx: None)
    rephraser.on_user_state_changed(_State("speaking"))  # speech, but no transcript ever
    await asyncio.wait_for(rephraser.wait_user_text(timeout=0.05), 1)


async def test_noise_without_words_closes_the_bubble_as_unclear():
    session, rephraser = make(lambda raw, ctx: None)
    say(session, "", final=False)  # "…" opened
    say(session, "  ", final=True)  # nothing was said
    await asyncio.wait_for(rephraser.wait_user_text(timeout=1), 1)

    assert session.published == [("…", False), (UNCLEAR["en"], True)]


async def test_placeholder_without_words_becomes_a_notice():
    session, rephraser = make(lambda raw, ctx: None)
    rephraser.placeholder_timeout = 0.05
    say(session, "", final=False)
    await asyncio.sleep(0.2)

    assert session.published[-1] == (UNCLEAR["en"], True)


async def test_careful_transcript_replaces_the_quick_one():
    seen = []

    async def rephrase(raw, context):
        seen.append(raw)
        return raw

    async def careful(timeout):
        return "No, uh, the the folder called Acme."  # still needs a clean-up

    session = FakeSession()
    rephraser = TranscriptRephraser(session, "en", rephrase=rephrase, careful=careful)
    session.on("user_input_transcribed", rephraser.on_transcribed)
    session.on("user_input_transcribed", lambda ev: session.published.append((ev.transcript, ev.is_final)))
    say(session, "Kendi mitik foder Acme pet testol.")
    await rephraser.wait_idle()

    assert seen == ["No, uh, the the folder called Acme."]
    assert session.published[-1] == ("No, the folder called Acme.", True)


async def test_noise_the_careful_listen_finds_empty_is_not_shown():
    """Background noise is not the user: hide the bubble and stop the agent's reply.

    (On near-silence the quick transcriber even echoed hint words like "Trip.com".)
    """

    async def rephrase(raw, context):
        raise AssertionError("noise must not be rephrased")

    async def careful(timeout):
        return ""

    session = FakeSession()
    interrupted = []
    session.interrupt = lambda: interrupted.append(True)
    rephraser = TranscriptRephraser(session, "en", rephrase=rephrase, careful=careful)
    session.on("user_input_transcribed", rephraser.on_transcribed)
    session.on("user_input_transcribed", lambda ev: session.published.append((ev.transcript, ev.is_final)))
    say(session, "Trip.com")
    await rephraser.wait_idle()

    assert session.published[-1] == ("", True)  # the app hides empty messages
    assert all("Trip.com" not in text for text, _ in session.published)
    assert interrupted == [True]


async def test_a_clean_careful_transcript_is_shown_without_another_model_call():
    """Saves a model call so the agent's reply is held back as briefly as possible."""

    async def rephrase(raw, context):
        raise AssertionError("not needed: the careful transcript is already clean")

    async def careful(timeout):
        return "Review the deck and propose changes."

    session = FakeSession()
    rephraser = TranscriptRephraser(session, "en", rephrase=rephrase, careful=careful)
    session.on("user_input_transcribed", rephraser.on_transcribed)
    session.on("user_input_transcribed", lambda ev: session.published.append((ev.transcript, ev.is_final)))
    say(session, "review the deck and proposed changes")
    await rephraser.wait_idle()

    assert session.published[-1] == ("Review the deck and propose changes.", True)


async def test_the_agent_answers_the_careful_words_not_its_own_hearing():
    """The model heard "without going"; the user said "Check on the screen"."""

    async def rephrase(raw, context):
        raise AssertionError("not needed: the careful transcript is already clean")

    async def careful(timeout):
        return "Check on the screen, you can see now."

    replies = []
    session = FakeSession()
    rephraser = TranscriptRephraser(
        session, "en", rephrase=rephrase, careful=careful, reply=replies.append
    )
    session.on("user_input_transcribed", rephraser.on_transcribed)
    say(session, "without going.")
    await rephraser.wait_idle()

    assert replies == ["Check on the screen, you can see now."]


async def test_no_reply_to_noise():
    async def rephrase(raw, context):
        raise AssertionError("noise must not be rephrased")

    async def careful(timeout):
        return ""

    replies = []
    session = FakeSession()
    session.interrupt = lambda: None
    rephraser = TranscriptRephraser(
        session, "en", rephrase=rephrase, careful=careful, reply=replies.append
    )
    session.on("user_input_transcribed", rephraser.on_transcribed)
    say(session, "Trip.com")
    await rephraser.wait_idle()

    assert replies == []


async def test_without_a_careful_listen_the_rephrased_words_are_answered():
    async def rephrase(raw, context):
        return "Can you open Excel?"

    replies = []
    session = FakeSession()
    rephraser = TranscriptRephraser(
        session, "en", rephrase=rephrase, reply=replies.append
    )
    session.on("user_input_transcribed", rephraser.on_transcribed)
    say(session, "um can you uh oven the the excel")
    await rephraser.wait_idle()

    assert replies == ["Can you open Excel?"]
