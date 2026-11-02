"""HireAce speaks first, and asks again if the greeting never starts."""

import asyncio
from types import SimpleNamespace

import agent


class FakeHandle:
    def __init__(self) -> None:
        self.interrupted = False

    def interrupt(self) -> None:
        self.interrupted = True


class FakeSession:
    """Records greeting requests; ``speak_on`` says which request starts speaking."""

    def __init__(self, speak_on: int | None) -> None:
        self.speak_on = speak_on
        self.requests: list[FakeHandle] = []
        self.handlers: dict[str, list] = {}

    def on(self, event, callback):
        self.handlers.setdefault(event, []).append(callback)

    def off(self, event, callback):
        self.handlers[event].remove(callback)

    def emit(self, event, payload):
        for callback in list(self.handlers.get(event, [])):
            callback(payload)

    def generate_reply(self, instructions):
        assert "HireAce" in instructions
        handle = FakeHandle()
        self.requests.append(handle)
        if len(self.requests) == self.speak_on:
            asyncio.get_running_loop().call_later(
                0.01,
                self.emit,
                "agent_state_changed",
                SimpleNamespace(new_state="speaking"),
            )
        return handle


async def test_greets_once_when_it_starts_speaking(monkeypatch):
    monkeypatch.setattr(agent, "GREET_TIMEOUT_S", 0.5)
    session = FakeSession(speak_on=1)

    await agent.greet_first(session)

    assert len(session.requests) == 1
    assert session.handlers == {"agent_state_changed": [], "user_input_transcribed": []}


async def test_asks_again_when_the_greeting_never_starts(monkeypatch):
    monkeypatch.setattr(agent, "GREET_TIMEOUT_S", 0.1)
    session = FakeSession(speak_on=2)

    await agent.greet_first(session)

    assert len(session.requests) == 2
    assert session.requests[0].interrupted  # the lost first one never plays late


async def test_no_second_greeting_once_the_user_spoke(monkeypatch):
    monkeypatch.setattr(agent, "GREET_TIMEOUT_S", 0.3)
    session = FakeSession(speak_on=None)
    asyncio.get_running_loop().call_later(
        0.05, session.emit, "user_input_transcribed", SimpleNamespace()
    )

    await agent.greet_first(session)

    assert len(session.requests) == 1


def test_one_idle_process_on_a_small_laptop():
    assert agent.server._num_idle_processes == 1
