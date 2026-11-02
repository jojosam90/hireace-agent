"""Where the agent's proposed actions go.

RemoteBackend talks to the gatekeeper service (start.ps1 runs it next to the
agent; the web app's Approve buttons talk to it too). LocalBackend runs the same
Gatekeeper in-process (console mode, tests), so the safety policy applies either way.
"""

from __future__ import annotations

import aiohttp

from browser import BrowserManager
from gatekeeper import Gatekeeper
from local_desktop import DesktopError, LocalDesktop
from office import Office


class LocalBackend:
    def __init__(
        self,
        browser: BrowserManager,
        session: str = "local",
        desktop: LocalDesktop | None = None,
        office: Office | None = None,
    ) -> None:
        self._browser = browser
        self._gatekeeper = Gatekeeper(browser, desktop=desktop, office=office)
        self.session = session

    async def submit(self, action: str, args: dict) -> dict:
        return await self._gatekeeper.submit(self.session, action, args)

    async def resolve(
        self, approval_id: str, *, approve: bool, channel: str = "voice"
    ) -> dict:
        return await self._gatekeeper.resolve(
            approval_id, approve=approve, channel=channel
        )

    async def status(self, approval_id: str) -> dict:
        return self._gatekeeper.status(approval_id)

    async def pending(self) -> list[dict]:
        return [a for a in self._gatekeeper.pending() if a["session"] == self.session]

    async def screenshot(self, **params) -> bytes | None:
        try:
            return await self._gatekeeper.screenshot(**params)
        except DesktopError:
            return None

    async def close(self) -> None:
        self._gatekeeper.end_session(self.session)
        await self._browser.close()


class RemoteBackend:
    def __init__(self, base_url: str, token: str, session: str) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"X-Gatekeeper-Token": token}
        self._http: aiohttp.ClientSession | None = None
        self.session = session

    async def _client(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession(
                headers=self._headers, timeout=aiohttp.ClientTimeout(total=60)
            )
        return self._http

    async def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        http = await self._client()
        try:
            async with http.request(method, self._base + path, json=body) as resp:
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as exc:
            return {"status": "error", "reason": f"Gatekeeper unavailable: {exc}"}

    async def submit(self, action: str, args: dict) -> dict:
        body = {"session": self.session, "action": action, "args": args}
        return await self._request("POST", "/v1/actions", body)

    async def resolve(
        self, approval_id: str, *, approve: bool, channel: str = "voice"
    ) -> dict:
        body = {"decision": "approve" if approve else "deny", "channel": channel}
        return await self._request("POST", f"/v1/approvals/{approval_id}", body)

    async def status(self, approval_id: str) -> dict:
        return await self._request("GET", f"/v1/approvals/{approval_id}")

    async def pending(self) -> list[dict]:
        http = await self._client()
        try:
            async with http.get(self._base + "/v1/approvals") as resp:
                resp.raise_for_status()
                items = await resp.json()
        except aiohttp.ClientError:
            return []
        return [a for a in items if a.get("session") == self.session]

    async def screenshot(self, **params) -> bytes | None:
        """PNG of the computer's screen (JPEG with format="jpeg"), or None if unavailable."""
        http = await self._client()
        try:
            async with http.get(self._base + "/v1/screenshot", params=params) as resp:
                return await resp.read() if resp.status == 200 else None
        except aiohttp.ClientError:
            return None

    async def close(self) -> None:
        # The call ended: clear its approval and any cards still waiting
        await self._request("POST", f"/v1/sessions/{self.session}/end")
        if self._http is not None:
            await self._http.close()
