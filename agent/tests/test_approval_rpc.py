import json

import pytest
from livekit import rtc
from test_gatekeeper import FakeBrowser

import approval_rpc
from action_backend import LocalBackend
from gatekeeper import Gatekeeper


def backend_for(session: str, gatekeeper: Gatekeeper) -> LocalBackend:
    backend = LocalBackend(FakeBrowser(), session=session)
    backend._gatekeeper = gatekeeper
    return backend


async def test_phone_lists_and_approves_this_calls_card(tmp_path):
    browser = FakeBrowser()
    gk = Gatekeeper(browser, audit_path=tmp_path / "audit.jsonl")
    backend = backend_for("call1", gk)
    waiting = await gk.submit("call1", "click", {"target": "Send"})

    listed = json.loads(await approval_rpc.list_pending(backend))
    payload = json.dumps({"id": waiting["approval_id"], "decision": "approve"})
    result = json.loads(await approval_rpc.decide(backend, payload))

    assert [a["id"] for a in listed] == [waiting["approval_id"]]
    assert result["status"] == "done" and browser.calls == [("click", "Send")]
    # Same as pressing Approve in the web app on the PC
    assert gk.status(waiting["approval_id"])["resolved_by"] == "web"


async def test_another_calls_card_cannot_be_approved(tmp_path):
    browser = FakeBrowser()
    gk = Gatekeeper(browser, audit_path=tmp_path / "audit.jsonl")
    other = await gk.submit("call2", "click", {"target": "Delete"})
    backend = backend_for("call1", gk)

    payload = json.dumps({"id": other["approval_id"], "decision": "approve"})
    result = json.loads(await approval_rpc.decide(backend, payload))

    assert json.loads(await approval_rpc.list_pending(backend)) == []
    assert result["status"] == "unknown" and browser.calls == []
    with pytest.raises(rtc.RpcError):
        await approval_rpc.decide(backend, json.dumps({"id": "x", "decision": "maybe"}))
