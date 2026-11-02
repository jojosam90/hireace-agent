"""Shared test fixtures."""

import pytest

import gmail as gmail_module
from gmail import NOT_READY, GmailError

SENDER = "sales@company.example"


class FakeGmail:
    """Gmail in the agent's browser: signed in (or not), recording what it sends."""

    def __init__(self, state: str = "ready") -> None:
        self.state = state
        self.sent: list[dict] = []
        self.opened = 0

    async def status(self) -> dict:
        return {"state": self.state, "email": SENDER if self.state == "ready" else ""}

    async def health(self) -> dict:
        ready = self.state == "ready"
        return {
            "checked": True,
            "connected": ready,
            "accounts": [{"browser": "Chrome", "email": SENDER}] if ready else [],
            "can_send": ready,
        }

    async def open(self, link: str = "") -> dict:
        self.opened += 1
        return await self.status()

    async def send(self, to, subject, text, attachments) -> dict:
        if self.state != "ready":
            raise GmailError(NOT_READY)
        self.sent.append(
            {"to": to, "subject": subject, "text": text, "attachments": attachments}
        )
        return {"from": SENDER}


@pytest.fixture(autouse=True)
def no_real_browsers(monkeypatch):
    """No test reads the PC's real browser tabs or sends from the real Gmail."""
    monkeypatch.setattr(
        gmail_module, "browser_tabs", lambda: {"windows": [], "selected": None}
    )

    def refuse(job):
        raise AssertionError(f"a test tried to really send: {job}")

    monkeypatch.setattr(gmail_module, "send_in_browser", refuse)


@pytest.fixture
def gmail() -> FakeGmail:
    return FakeGmail()
