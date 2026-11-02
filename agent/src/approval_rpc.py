"""The web app's Approve buttons, over the call's own LiveKit connection.

The web app may run on a server (e.g. Vercel, opened on a phone) that cannot reach
the gatekeeper on this PC, so it asks the agent instead: the agent lists this
call's waiting actions and passes the user's decision on as a web approval.
"""

from __future__ import annotations

import json

from livekit import rtc

# Must match the web app's components/app/approval-panel.tsx
APPROVALS_METHOD = "hireace.approvals"
DECIDE_METHOD = "hireace.decide"


async def list_pending(backend) -> str:
    return json.dumps(await backend.pending())


async def decide(backend, payload: str) -> str:
    body = json.loads(payload or "{}")
    approval_id = str(body.get("id", ""))
    decision = body.get("decision")
    if decision not in ("approve", "deny"):
        raise rtc.RpcError(1, "decision must be approve or deny")
    # Only this call's own cards
    if approval_id not in {a["id"] for a in await backend.pending()}:
        return json.dumps({"status": "unknown", "reason": "No such approval."})
    result = await backend.resolve(
        approval_id, approve=decision == "approve", channel="web"
    )
    return json.dumps(result)


def register(room: rtc.Room, backend) -> None:
    async def on_list(_: rtc.RpcInvocationData) -> str:
        return await list_pending(backend)

    async def on_decide(data: rtc.RpcInvocationData) -> str:
        return await decide(backend, data.payload)

    room.local_participant.register_rpc_method(APPROVALS_METHOD, on_list)
    room.local_participant.register_rpc_method(DECIDE_METHOD, on_decide)
