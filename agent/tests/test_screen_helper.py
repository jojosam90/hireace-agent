import asyncio

import screen_helper
from screen_helper import ScreenHelper


class FakeSession:
    def __init__(self) -> None:
        self.replies: list[str] = []

    def generate_reply(self, *, instructions):
        self.replies.append(instructions)


def make(answers, monkeypatch):
    monkeypatch.setattr(screen_helper, "WATCH_DELAY_SECONDS", 0.01)
    helper = ScreenHelper(backend=None)
    looked = []

    async def look(question):
        looked.append(question)
        return answers.pop(0)

    helper.look = look
    return helper, looked


async def _settle():
    await asyncio.sleep(0.1)


async def test_quiet_when_nothing_needs_attention(monkeypatch):
    helper, looked = make(["OK"], monkeypatch)
    session = FakeSession()
    helper.after_action(session, "open_file")
    await _settle()
    assert len(looked) == 1 and session.replies == []


async def test_reports_a_blocker_once(monkeypatch):
    alert = "A 'Save changes?' dialog is open in Word."
    helper, _ = make([alert, alert], monkeypatch)
    session = FakeSession()
    helper.after_action(session, "office_save")
    await _settle()
    helper.after_action(session, "screen_click")
    await _settle()
    assert len(session.replies) == 1 and alert in session.replies[0]


async def test_a_burst_of_actions_is_checked_once(monkeypatch):
    helper, looked = make(["OK"], monkeypatch)
    session = FakeSession()
    for _ in range(5):
        helper.after_action(session, "screen_key")
    await _settle()
    assert len(looked) == 1


async def test_read_only_actions_are_not_watched(monkeypatch):
    helper, looked = make([], monkeypatch)
    helper.after_action(FakeSession(), "find_files")
    await _settle()
    assert looked == []


async def test_background_question_is_answered_to_the_agent(monkeypatch):
    helper, _ = make(["Yes, ACME_Proposal.docx is open in Word."], monkeypatch)
    session = FakeSession()
    helper.ask_in_background(session, "Is the proposal open?")
    await _settle()
    assert "ACME_Proposal.docx is open" in session.replies[0]
