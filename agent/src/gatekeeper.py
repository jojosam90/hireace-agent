"""Gatekeeper: the only component allowed to act on the user's computer.

Modeled on Meta Muse's "Sentinel": the voice agent can only *propose* actions.
The gatekeeper classifies each one with the deterministic policy in policy.py,
executes allowed actions in the agent's browser or on the desktop, parks risky
ones until the user approves (by voice or in the web app), refuses payments
outright, and appends every decision to an audit log.

Run as a service:  uv run src/gatekeeper.py   (listens on 127.0.0.1 only)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

from aiohttp import web
from dotenv import load_dotenv

from browser import BrowserError, BrowserManager
from emailer import Emailer, EmailError
from gmail import NOT_READY, GmailError, GmailWindow
from local_desktop import DesktopError, LocalDesktop
from office import Office, OfficeError
from policy import ASK, DENY, PageContext, decide
from quotation import QuoteError
from settings import Settings, data_dir

logger = logging.getLogger("gatekeeper")

# Actions carried out with the computer's real mouse/keyboard/windows.
# Coordinates arrive on the model's 0-1000 scale and are converted to pixels.
DESKTOP_ACTIONS = {
    "screen_move",
    "screen_click",
    "screen_drag",
    "screen_scroll",
    "screen_type",
    "screen_key",
    "screenshot",
    "list_windows",
    "focus_window",
    "find_browser_tab",
    "open_browser_item",
    "read_browser_window",
    "close_window",
    "open_app",
    "find_files",
    "open_file",
}

# Word, Excel and PowerPoint through COM (office.py): no screen involved
OFFICE_ACTIONS = {
    "office_read",
    "office_go_to",
    "word_edit",
    "excel_set_cells",
    "ppt_edit",
    "office_save",
    "make_quotation",
    "save_quotation",
}

# Sent from the Gmail signed in in the agent's browser (gmail.py)
GMAIL_ACTIONS = {"send_email", "send_quotation"}

# Always asked, even after the user approved something else in the call: each
# quotation is approved before it is saved, and every email before it is sent
ALWAYS_ASK = {"save_quotation", "send_quotation", "send_email"}


def reply_subject(subject: str) -> str:
    """The inquiry's subject as a reply: "Re: <subject>" (once)."""
    subject = subject.strip() or "Quotation"
    return subject if re.match(r"(?i)re:", subject) else f"Re: {subject}"


_CARD_LIKE = re.compile(r"(?:\d[ -]?){12,19}")


def _redact(args: dict) -> dict:
    return {
        k: _CARD_LIKE.sub("[redacted-number]", v) if isinstance(v, str) else v
        for k, v in args.items()
    }


def _describe(action: str, args: dict) -> str:
    if action == "click":
        verb = "double-click" if args.get("double") else "click"
        return f"{verb} {args.get('target')!r}"
    if action == "type_text":
        return f"type into {args.get('target')!r}"
    if action == "open_url":
        return f"open {args.get('url')}"
    if action == "press_key":
        return f"press {args.get('key')}"
    if action in ("screen_click", "screen_drag"):
        return "click on your computer's screen"
    if action == "screen_type":
        return "type on your computer"
    if action == "screen_key":
        return f"press {args.get('keys')} on your computer"
    if action == "close_window":
        return f"close the window {args.get('title')!r}"
    if action == "open_file":
        return f"open {PureWindowsPath(str(args.get('path', ''))).name}"
    if action == "office_save":
        return f"save the {args.get('app')} file"
    if action == "send_email":
        to = args.get("to") or []
        to = ", ".join(to) if isinstance(to, list) else str(to)
        return f"email {args.get('subject')!r} to {to}"
    if action == "send_quotation":
        return f"email the quotation to {args.get('to')}"
    if action == "save_quotation":
        number = args.get("quote_number") or "the quotation"
        return f"save {number} as Excel and PDF"
    return action


@dataclass
class Approval:
    id: str
    session: str
    action: str
    args: dict
    summary: str
    reason: str
    created: float
    state: str = "pending"  # pending | done | rejected | denied | expired | failed
    resolved_by: str | None = None
    result: dict = field(default_factory=dict)

    def public(self) -> dict:
        return {
            "id": self.id,
            "session": self.session,
            "action": self.action,
            # Lets the web app word the request in its own language
            "args": _redact(self.args),
            "summary": self.summary,
            "reason": self.reason,
            "created": self.created,
            "state": self.state,
            "resolved_by": self.resolved_by,
            "result": self.result,
        }


class Gatekeeper:
    def __init__(
        self,
        browser: BrowserManager,
        *,
        desktop: LocalDesktop | None = None,
        office: Office | None = None,
        emailer: Emailer | None = None,
        audit_path: Path | None = None,
        approval_ttl: float = 120.0,
    ) -> None:
        self._browser = browser
        self._desktop = desktop
        self._office = office
        self.emailer = emailer
        self._audit_path = audit_path
        self._ttl = approval_ttl
        self._approvals: dict[str, Approval] = {}
        # Calls (sessions) where the user approved an action: from then on nothing
        # else asks during that call. Payments are DENY, never ASK, so they stay
        # blocked. A new call is a new session.
        self._approved_sessions: set[str] = set()
        # Calls running now, oldest first: the panel on this PC mirrors the latest
        self._live_calls: list[str] = []

    def start_session(self, session: str) -> None:
        if session not in self._live_calls:
            self._live_calls.append(session)

    def live_call(self) -> str | None:
        return self._live_calls[-1] if self._live_calls else None

    async def submit(self, session: str, action: str, args: dict) -> dict:
        if action in DESKTOP_ACTIONS and self._desktop is None:
            return {"status": "error", "reason": "Desktop control is not enabled."}
        if action in OFFICE_ACTIONS and self._office is None:
            return {"status": "error", "reason": "Office control is not enabled."}
        if action in GMAIL_ACTIONS and self.emailer is None:
            return {"status": "error", "reason": "Email is not enabled."}
        # Checked before asking: the user is never asked to approve an email that
        # cannot be sent
        if (
            action in GMAIL_ACTIONS
            and (await self.emailer.gmail.status())["state"] != "ready"
        ):
            return {"status": "error", "reason": NOT_READY}
        if action == "send_quotation":
            # The reply to the inquiry: "Re: <its subject>". The address is the
            # inquiry's sender as the model read it from the email; the approval
            # card shows it, and every quotation email is asked.
            args = {**args, "subject": reply_subject(str(args.get("subject", "")))}
        decision = decide(action, args, await self._context(action, args))

        if (
            decision.verdict == ASK
            and session in self._approved_sessions
            and action not in ALWAYS_ASK
        ):
            self._audit(
                session,
                action,
                args,
                "allow",
                f"Approved earlier this call: {decision.reason}",
            )
            return await self._execute(action, args)

        self._audit(session, action, args, decision.verdict, decision.reason)

        if decision.verdict == DENY:
            return {"status": "denied", "reason": decision.reason}

        if decision.verdict == ASK:
            approval = Approval(
                id=uuid.uuid4().hex[:8],
                session=session,
                action=action,
                args=args,
                summary=_describe(action, args),
                reason=decision.reason,
                created=time.time(),
            )
            self._approvals[approval.id] = approval
            return {
                "status": "needs_approval",
                "approval_id": approval.id,
                "summary": approval.summary,
                "reason": approval.reason,
            }

        return await self._execute(action, args)

    async def resolve(self, approval_id: str, *, approve: bool, channel: str) -> dict:
        approval = self._approvals.get(approval_id)
        if approval is None:
            return {"status": "unknown", "reason": "No such approval."}
        if approval.state != "pending":
            return {"status": approval.state, **approval.result}

        approval.resolved_by = channel
        if time.time() - approval.created >= self._ttl:
            approval.state = "expired"
        elif not approve:
            approval.state = "rejected"
        else:
            # Re-check: the page may have changed since the request was parked.
            # A DENY here (e.g. payment form appeared) cannot be overridden.
            ctx = await self._context(approval.action, approval.args)
            decision = decide(approval.action, approval.args, ctx)
            if decision.verdict == DENY:
                approval.state = "denied"
                approval.result = {"reason": decision.reason}
            else:
                self._approved_sessions.add(approval.session)
                approval.result = await self._execute(approval.action, approval.args)
                approval.state = (
                    "done" if approval.result["status"] == "done" else "failed"
                )

        self._audit(
            approval.session,
            approval.action,
            approval.args,
            f"approval:{approval.state}",
            f"by {channel}",
        )
        return {"status": approval.state, **approval.result}

    def pending(self) -> list[dict]:
        now = time.time()
        return [
            a.public()
            for a in self._approvals.values()
            if a.state == "pending" and now - a.created < self._ttl
        ]

    def end_session(self, session: str) -> None:
        """The call ended: drop its approval and any cards still waiting."""
        self._approved_sessions.discard(session)
        if session in self._live_calls:
            self._live_calls.remove(session)
        for approval in self._approvals.values():
            if approval.session == session and approval.state == "pending":
                approval.state = "expired"

    def status(self, approval_id: str) -> dict:
        approval = self._approvals.get(approval_id)
        return approval.public() if approval else {"state": "unknown"}

    def audit_tail(self, limit: int = 50) -> list[dict]:
        if not self._audit_path or not self._audit_path.exists():
            return []
        lines = self._audit_path.read_text(encoding="utf-8").splitlines()[-limit:]
        return [json.loads(line) for line in lines]

    async def screenshot(self, **params) -> bytes:
        if self._desktop is None:
            raise DesktopError("Desktop control is not enabled.")
        return await self._desktop.screenshot(**params)

    async def _context(self, action: str, args: dict) -> PageContext:
        if action in OFFICE_ACTIONS or action in ("send_email", "send_quotation"):
            return PageContext()  # no web page involved
        if action in DESKTOP_ACTIONS:
            return await self._screen_context(action, args)
        try:
            info = await self._browser.page_context()
            attrs = {}
            if action == "type_text":
                attrs = await self._browser.field_attributes(
                    str(args.get("target", ""))
                )
            return PageContext(
                url=str(info.get("url", "")),
                payment_fields=bool(info.get("payment_fields")),
                field=attrs,
            )
        except BrowserError:
            return PageContext()

    async def _screen_context(self, action: str, args: dict) -> PageContext:
        # What the browser shows under the pointer / in its focused field, so the
        # same payment and approval rules apply to raw mouse and keyboard input.
        if self._desktop is None:
            return PageContext()  # nothing to act on; execution reports the error
        point = (None, None)
        try:
            if "x" in args and "y" in args:
                point = await self._desktop.to_pixels(args["x"], args["y"])
            info = await self._browser.screen_context(*point)
        except (BrowserError, DesktopError):
            return PageContext()
        # Input reaches the agent's browser only if its window has the focus and,
        # for clicks, the point is on its page; anything else is the user's computer
        in_browser = bool(info.get("focused")) and (
            point[0] is None or bool(info.get("inside"))
        )
        return PageContext(
            url=str(info.get("url", "")),
            payment_fields=bool(info.get("payment_fields")),
            field=dict(info.get("field") or {}),
            target=str(info.get("target", "")),
            in_browser=in_browser,
        )

    async def _execute_desktop(self, action: str, args: dict) -> dict:
        d = self._desktop
        if d is None:
            raise DesktopError("Desktop control is not enabled.")
        if action in ("screen_move", "screen_click", "screen_drag"):
            x, y = await d.to_pixels(args["x"], args["y"])
            if action == "screen_move":
                return await d.act("move", x=x, y=y)
            if action == "screen_click":
                return await d.act(
                    "click",
                    x=x,
                    y=y,
                    button=args.get("button", "left"),
                    clicks=int(args.get("clicks", 1)),
                )
            to_x, to_y = await d.to_pixels(args["to_x"], args["to_y"])
            return await d.act("drag", x=x, y=y, to_x=to_x, to_y=to_y)
        if action == "screen_scroll":
            amount = abs(int(args.get("amount", 5)))
            params = {"amount": amount if args.get("direction") == "up" else -amount}
            if "x" in args and "y" in args:
                params["x"], params["y"] = await d.to_pixels(args["x"], args["y"])
            return await d.act("scroll", **params)
        if action == "screen_type":
            return await d.act("type", text=str(args.get("text", "")))
        if action == "screen_key":
            keys = [
                k.strip().lower()
                for k in str(args.get("keys", "")).split("+")
                if k.strip()
            ]
            if len(keys) == 1:
                return await d.act("press", key=keys[0])
            return await d.act("hotkey", keys=keys)
        if action == "screenshot":
            width, height = await d.size()
            return {"width": width, "height": height}
        if action == "list_windows":
            return await d.act("windows")
        if action in ("focus_window", "close_window"):
            return await d.act(action, title=str(args.get("title", "")))
        if action == "find_browser_tab":
            return await d.find_browser_tab(str(args.get("text", "")))
        if action == "open_browser_item":
            return await d.open_browser_item(str(args.get("text", "")))
        if action == "read_browser_window":
            return await d.read_browser_window(str(args.get("text", "")))
        if action == "find_files":
            return await d.find_files(
                str(args.get("query", "")), kind=str(args.get("kind", "any"))
            )
        if action == "open_file":
            return await d.open_file(str(args.get("path", "")))
        return await d.act("open_app", app=args.get("app"))

    async def _send_email(self, args: dict) -> dict:
        args = dict(args)
        files = list(args.pop("attachments", None) or [])
        # attach_open: apps whose open document goes along. Its saved file is what
        # is sent, so unsaved edits (the highlighted changes) must be saved first.
        for app in args.pop("attach_open", None) or []:
            if self._office is None:
                raise EmailError(
                    "Office control is not enabled, so no open file can be attached."
                )
            info = await self._office.run("office_path", {"app": app})
            if not info["saved"]:
                raise EmailError(
                    f"The {app} file has unsaved changes: save it (office_save) and send again."
                )
            files.append(info["path"])
        return await self.emailer.send(attachments=files, **args)

    async def _execute(self, action: str, args: dict, *, retry: bool = True) -> dict:
        try:
            if action == "send_email":
                return {"status": "done", "result": await self._send_email(args)}
            if action == "send_quotation":
                return {
                    "status": "done",
                    "result": await self.emailer.send_quotation(**args),
                }
            if action in OFFICE_ACTIONS:
                return {
                    "status": "done",
                    "result": await self._office.run(action, args),
                }
            if action in DESKTOP_ACTIONS:
                return {
                    "status": "done",
                    "result": await self._execute_desktop(action, args),
                }
            result = await getattr(self._browser, action)(**args)
            return {"status": "done", "result": result}
        except (
            BrowserError,
            DesktopError,
            OfficeError,
            EmailError,
            GmailError,
            QuoteError,
        ) as exc:
            return {"status": "error", "reason": str(exc)}
        except (TypeError, KeyError, ValueError) as exc:
            return {"status": "error", "reason": f"Bad arguments: {exc}"}
        except Exception as exc:
            # Typically the user closed the browser window mid-action (the browser
            # then forgets it): try once more, which opens a fresh window.
            if retry and action not in DESKTOP_ACTIONS | OFFICE_ACTIONS | GMAIL_ACTIONS:
                logger.warning("browser action %s failed (%s); retrying", action, exc)
                return await self._execute(action, args, retry=False)
            logger.exception("action %s failed", action)
            return {"status": "error", "reason": f"The action failed: {exc}"}

    def _audit(self, session: str, action: str, args: dict, verdict: str, reason: str):
        if not self._audit_path:
            return
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "session": session,
            "action": action,
            "args": _redact(args),
            "verdict": verdict,
            "reason": reason,
        }
        with self._audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


# --- HTTP service --------------------------------------------------------------


def create_app(
    gatekeeper: Gatekeeper, token: str, settings: Settings | None = None
) -> web.Application:
    @web.middleware
    async def auth(request: web.Request, handler):
        if (
            request.path != "/healthz"
            and request.headers.get("X-Gatekeeper-Token") != token
        ):
            raise web.HTTPUnauthorized()
        return await handler(request)

    async def submit(request: web.Request) -> web.Response:
        body = await request.json()
        result = await gatekeeper.submit(
            str(body.get("session", "default")),
            str(body.get("action", "")),
            dict(body.get("args") or {}),
        )
        return web.json_response(result)

    async def resolve(request: web.Request) -> web.Response:
        body = await request.json()
        channel = str(body.get("channel", "web"))
        if channel not in {"web", "voice"}:
            raise web.HTTPBadRequest(text="channel must be web or voice")
        result = await gatekeeper.resolve(
            request.match_info["approval_id"],
            approve=body.get("decision") == "approve",
            channel=channel,
        )
        return web.json_response(result)

    async def pending(_: web.Request) -> web.Response:
        return web.json_response(gatekeeper.pending())

    async def end_session(request: web.Request) -> web.Response:
        gatekeeper.end_session(request.match_info["session"])
        return web.json_response({"ended": True})

    async def start_session(request: web.Request) -> web.Response:
        gatekeeper.start_session(request.match_info["session"])
        return web.json_response({"started": True})

    async def live_call(_: web.Request) -> web.Response:
        return web.json_response({"room": gatekeeper.live_call()})

    async def status(request: web.Request) -> web.Response:
        return web.json_response(gatekeeper.status(request.match_info["approval_id"]))

    async def audit(request: web.Request) -> web.Response:
        limit = min(int(request.query.get("limit", "50")), 500)
        return web.json_response(gatekeeper.audit_tail(limit))

    async def screenshot(request: web.Request) -> web.Response:
        params = {
            k: v
            for k, v in request.query.items()
            if k in ("format", "quality", "width")
        }
        try:
            body = await gatekeeper.screenshot(**params)
            content_type = (
                "image/jpeg" if params.get("format") == "jpeg" else "image/png"
            )
            return web.Response(body=body, content_type=content_type)
        except DesktopError as exc:
            raise web.HTTPServiceUnavailable(text=str(exc)) from exc

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    # --- Settings page ---

    async def get_settings(_: web.Request) -> web.Response:
        if settings is None:
            raise web.HTTPServiceUnavailable(text="Settings are not enabled.")
        return web.json_response(settings.public())

    async def save_settings(request: web.Request) -> web.Response:
        if settings is None:
            raise web.HTTPServiceUnavailable(text="Settings are not enabled.")
        errors = settings.save(dict(await request.json()))
        return web.json_response({"saved": not errors, "errors": errors})

    # --- Gmail in the agent's browser (Settings > Email) ---

    def gmail() -> GmailWindow:
        if gatekeeper.emailer is None:
            raise web.HTTPServiceUnavailable(text="Email is not enabled.")
        return gatekeeper.emailer.gmail

    async def gmail_status(_: web.Request) -> web.Response:
        return web.json_response(await gmail().status())

    async def gmail_health(_: web.Request) -> web.Response:
        return web.json_response(await gmail().health())

    async def gmail_open(request: web.Request) -> web.Response:
        body = await request.json() if request.can_read_body else {}
        try:
            return web.json_response(await gmail().open(str(body.get("link", ""))))
        except (BrowserError, GmailError) as exc:
            return web.json_response(
                {"state": "closed", "email": "", "reason": str(exc)}
            )

    async def gmail_test(request: web.Request) -> web.Response:
        gmail()
        to = str((await request.json()).get("to", ""))
        try:
            result = await gatekeeper.emailer.send_test(to)
        except EmailError as exc:
            return web.json_response({"sent": False, "reason": str(exc)})
        return web.json_response(result)

    app = web.Application(middlewares=[auth])
    app.add_routes(
        [
            web.post("/v1/actions", submit),
            web.get("/v1/approvals", pending),
            web.post("/v1/sessions/{session}/start", start_session),
            web.post("/v1/sessions/{session}/end", end_session),
            web.get("/v1/calls", live_call),
            web.get("/v1/approvals/{approval_id}", status),
            web.post("/v1/approvals/{approval_id}", resolve),
            web.get("/v1/audit", audit),
            web.get("/v1/screenshot", screenshot),
            web.get("/v1/settings", get_settings),
            web.post("/v1/settings", save_settings),
            web.get("/v1/gmail", gmail_status),
            web.get("/v1/gmail/health", gmail_health),
            web.post("/v1/gmail/open", gmail_open),
            web.post("/v1/gmail/test", gmail_test),
            web.get("/healthz", health),
        ]
    )
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.environ["GATEKEEPER_TOKEN"]
    port = int(os.environ.get("PORT", "8080"))
    folder = data_dir()
    # The agent's own Chrome profile: sign in to Gmail and websites there once
    browser = BrowserManager(profile_dir=folder / "chrome-profile")
    audit_path = Path(os.environ.get("AUDIT_LOG", folder / "audit.jsonl"))
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    load_dotenv(".env.local")  # the defaults for Settings
    settings = Settings(folder / "settings.json")
    settings.apply()
    gatekeeper = Gatekeeper(
        browser,
        desktop=LocalDesktop(),
        office=Office(),
        # Gmail signed in in this same browser window
        emailer=Emailer(GmailWindow(browser)),
        audit_path=audit_path,
    )
    # Loopback only: this service drives the real mouse and keyboard
    # No line per request: the app checks for approvals every 1.5 s, which filled
    # the log (and the disk) with nothing useful
    web.run_app(
        create_app(gatekeeper, token, settings),
        host="127.0.0.1",
        port=port,
        access_log=None,
    )


if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    main()
