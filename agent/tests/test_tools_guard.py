import pytest
from livekit.agents.llm import ToolError

from tools import HARD_STOP_FAILURES, WARN_FAILURES, BrowserTools


class FakeBackend:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail = True

    async def submit(self, action, args):
        self.calls.append(action)
        if self.fail and action == "click":
            return {
                "status": "error",
                "reason": "I could not find a visible control named 'x'.",
            }
        return {"status": "done", "result": {"ok": True}}


async def test_repeated_failures_warn_then_stop_guessing():
    backend = FakeBackend()
    tools = BrowserTools(backend)

    messages = []
    for _ in range(HARD_STOP_FAILURES):
        with pytest.raises(ToolError) as exc:
            await tools._run(None, "click", {"target": "x"})
        messages.append(str(exc.value))
    assert "do not keep guessing" not in messages[WARN_FAILURES - 2]
    assert "do not keep guessing" in messages[WARN_FAILURES - 1]

    # Further clicks are not even attempted...
    with pytest.raises(ToolError, match="Not attempted"):
        await tools._run(None, "click", {"target": "y"})
    assert backend.calls.count("click") == HARD_STOP_FAILURES

    # ...until something else succeeds, e.g. reading the page
    await tools._run(None, "read_page", {})
    backend.fail = False
    assert await tools._run(None, "click", {"target": "y"}) == {"ok": True}


class ApprovalBackend:
    """One action waiting for approval, id "a1"."""

    def __init__(self) -> None:
        self.resolved: list[tuple[str, bool]] = []

    async def pending(self):
        return [{"id": "a1", "session": "s"}]

    async def resolve(self, approval_id, *, approve):
        if approval_id != "a1":
            return {"status": "unknown", "reason": "No such approval."}
        self.resolved.append((approval_id, approve))
        return {"status": "done", "result": {"ok": True}}


@pytest.mark.parametrize("given_id", ["", "garbled-id"])
async def test_yes_approves_what_is_waiting_even_without_the_right_id(given_id):
    backend = ApprovalBackend()
    tools = BrowserTools(backend)

    result = await tools._resolve(given_id, approve=True)

    assert result["status"] == "done"
    assert backend.resolved == [("a1", True)]


async def test_approving_with_nothing_waiting_says_so():
    backend = ApprovalBackend()
    backend.pending = lambda: _empty()
    tools = BrowserTools(backend)

    with pytest.raises(ToolError, match="Nothing is waiting"):
        await tools._resolve("", approve=True)


async def _empty():
    return []


async def test_needing_approval_is_said_out_loud():
    """The Approve button shows in the app and the agent tells the user about it:
    they may not be looking at the screen."""

    class AskingBackend:
        async def submit(self, action, args):
            return {
                "status": "needs_approval",
                "approval_id": "a1",
                "summary": "click 'Send'",
            }

        async def status(self, approval_id):
            return {"state": "pending"}

    class Context:
        session = None

    tools = BrowserTools(AskingBackend())
    result = await tools._run(Context(), "click", {"target": "Send"})
    assert result["status"] == "needs_approval"
    assert (
        result["say_now"]
        == "Please approve: click 'Send'. Tap Approve on screen, or say yes."
    )
    for task in list(tools._watchers):
        task.cancel()
