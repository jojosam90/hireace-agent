import json

import pytest
from conftest import FakeGmail

from gatekeeper import Gatekeeper


class FakeBrowser:
    """Records executed actions instead of driving a real browser."""

    def __init__(self, url: str = "https://example.com", payment_fields: bool = False):
        self.url = url
        self.payment_fields = payment_fields
        self.field: dict = {}
        self.calls: list[tuple] = []

    async def page_context(self):
        return {"url": self.url, "payment_fields": self.payment_fields}

    async def field_attributes(self, target):
        return self.field

    async def open_url(self, url):
        self.calls.append(("open_url", url))
        self.url = url
        return {"url": url, "title": "t"}

    async def click(self, target, double=False):
        self.calls.append(("click", target, double) if double else ("click", target))
        return {"url": self.url, "title": "t"}

    async def type_text(self, target, text):
        self.calls.append(("type_text", target, text))
        return {"target": target, "url": self.url}

    async def read_page(self):
        return {"url": self.url, "title": "t", "text": "hi", "truncated": False}

    async def open_browser(self):
        self.calls.append(("open_browser",))
        return {"url": self.url, "title": "t"}

    async def close_browser(self):
        self.calls.append(("close_browser",))
        return {"closed": True}


@pytest.fixture
def audit_path(tmp_path):
    return tmp_path / "audit.jsonl"


async def test_allowed_actions_execute_immediately(audit_path):
    browser = FakeBrowser()
    gk = Gatekeeper(browser, audit_path=audit_path)

    result = await gk.submit("room1", "open_url", {"url": "https://youtube.com"})

    assert result["status"] == "done"
    assert browser.calls == [("open_url", "https://youtube.com")]


async def test_payment_actions_are_denied_and_never_executed(audit_path):
    browser = FakeBrowser()
    gk = Gatekeeper(browser, audit_path=audit_path)

    result = await gk.submit("room1", "click", {"target": "Buy now"})

    assert result["status"] == "denied"
    assert browser.calls == []


async def test_risky_action_waits_for_approval_then_executes(audit_path):
    browser = FakeBrowser()
    gk = Gatekeeper(browser, audit_path=audit_path)

    pending = await gk.submit("room1", "click", {"target": "Send"})
    assert pending["status"] == "needs_approval"
    assert browser.calls == []
    assert [p["id"] for p in gk.pending()] == [pending["approval_id"]]

    done = await gk.resolve(pending["approval_id"], approve=True, channel="web")

    assert done["status"] == "done"
    assert browser.calls == [("click", "Send")]
    assert gk.pending() == []
    assert gk.status(pending["approval_id"])["resolved_by"] == "web"


async def test_one_approval_covers_every_later_action_in_the_call(audit_path):
    browser = FakeBrowser()
    gk = Gatekeeper(browser, audit_path=audit_path)

    first = await gk.submit("call1", "click", {"target": "Send"})
    assert first["status"] == "needs_approval"
    await gk.resolve(first["approval_id"], approve=True, channel="voice")
    again = await gk.submit("call1", "click", {"target": "Send"})
    browser.field = {"type": "password"}
    password = await gk.submit(
        "call1", "type_text", {"target": "Password", "text": "x"}
    )
    next_call = await gk.submit("call2", "click", {"target": "Delete"})

    assert again["status"] == "done"  # no second question
    assert password["status"] == "done"  # other kinds of action are covered too
    assert next_call["status"] == "needs_approval"  # a new call starts fresh
    assert browser.calls == [
        ("click", "Send"),
        ("click", "Send"),
        ("type_text", "Password", "x"),
    ]


async def test_ending_the_call_clears_its_approval_and_waiting_cards(audit_path):
    gk = Gatekeeper(FakeBrowser(), audit_path=audit_path)
    first = await gk.submit("call1", "click", {"target": "Send"})
    await gk.resolve(first["approval_id"], approve=True, channel="web")
    waiting = await gk.submit("call2", "click", {"target": "Delete"})

    gk.end_session("call1")
    gk.end_session("call2")

    assert gk.pending() == []  # no stale card from a finished call
    assert (await gk.resolve(waiting["approval_id"], approve=True, channel="web"))[
        "status"
    ] == "expired"
    assert (await gk.submit("call1", "click", {"target": "Send"}))[
        "status"
    ] == "needs_approval"


async def test_approvals_never_unlock_payments(audit_path):
    browser = FakeBrowser()
    gk = Gatekeeper(browser, audit_path=audit_path)

    first = await gk.submit("call1", "click", {"target": "Submit"})
    await gk.resolve(first["approval_id"], approve=True, channel="web")
    pay = await gk.submit("call1", "click", {"target": "Place your order"})

    assert pay["status"] == "denied"


async def test_rejected_approval_grants_nothing(audit_path):
    browser = FakeBrowser()
    gk = Gatekeeper(browser, audit_path=audit_path)

    first = await gk.submit("call1", "click", {"target": "Send"})
    await gk.resolve(first["approval_id"], approve=False, channel="voice")
    again = await gk.submit("call1", "click", {"target": "Send"})

    assert again["status"] == "needs_approval"
    assert browser.calls == []


async def test_denied_approval_does_not_execute(audit_path):
    browser = FakeBrowser()
    gk = Gatekeeper(browser, audit_path=audit_path)

    pending = await gk.submit("room1", "click", {"target": "Delete account"})
    result = await gk.resolve(pending["approval_id"], approve=False, channel="voice")

    assert result["status"] == "rejected"
    assert browser.calls == []


async def test_policy_is_rechecked_at_execution_time(audit_path):
    # Approved while on a normal page, but the page became a payment page before
    # the approval arrived: the payment rule must still win.
    browser = FakeBrowser()
    gk = Gatekeeper(browser, audit_path=audit_path)

    pending = await gk.submit("room1", "click", {"target": "Submit"})
    browser.payment_fields = True
    result = await gk.resolve(pending["approval_id"], approve=True, channel="voice")

    assert result["status"] == "denied"
    assert browser.calls == []


async def test_expired_approvals_cannot_be_used(audit_path):
    browser = FakeBrowser()
    gk = Gatekeeper(browser, audit_path=audit_path, approval_ttl=0)

    pending = await gk.submit("room1", "click", {"target": "Send"})
    result = await gk.resolve(pending["approval_id"], approve=True, channel="web")

    assert result["status"] == "expired"
    assert browser.calls == []


async def test_every_decision_is_audited_with_card_numbers_redacted(audit_path):
    browser = FakeBrowser()
    gk = Gatekeeper(browser, audit_path=audit_path)

    await gk.submit("room1", "open_url", {"url": "https://example.com"})
    await gk.submit(
        "room1", "type_text", {"target": "Notes", "text": "4111 1111 1111 1111"}
    )

    entries = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert [e["verdict"] for e in entries] == ["allow", "deny"]
    assert "4111" not in audit_path.read_text()


async def test_browser_can_be_opened_and_closed_on_request(audit_path):
    browser = FakeBrowser()
    gk = Gatekeeper(browser, audit_path=audit_path)

    assert (await gk.submit("room1", "open_browser", {}))["status"] == "done"
    assert (await gk.submit("room1", "close_browser", {}))["status"] == "done"
    assert browser.calls == [("open_browser",), ("close_browser",)]


# --- Desktop control ------------------------------------------------------------


class FakeDesktop:
    def __init__(self) -> None:
        self.ops: list[tuple] = []

    async def act(self, op, **params):
        self.ops.append((op, params))
        if op == "windows":
            return {"windows": [{"id": "0x1", "title": "Chromium"}]}
        return {"ok": True}

    async def to_pixels(self, x, y):
        return round(x / 1000 * 1439), round(y / 1000 * 899)

    async def screenshot(self):
        return b"\x89PNG fake"

    async def find_files(self, query, kind="any"):
        self.ops.append(("find_files", {"query": query, "kind": kind}))
        return {"matches": [], "total_found": 0, "searched_everywhere": True}

    async def open_file(self, path):
        self.ops.append(("open_file", {"path": path}))
        return {"opened": path}


class ScreenBrowser(FakeBrowser):
    """in_browser: the agent's Chrome is focused and under the pointer."""

    def __init__(self, target: str = "", in_browser: bool = True, **kw):
        super().__init__(**kw)
        self.target = target
        self.in_browser = in_browser

    async def screen_context(self, x=None, y=None):
        self.asked_point = (x, y)
        return {
            "url": self.url,
            "target": self.target,
            "field": {},
            "payment_fields": self.payment_fields,
            "focused": self.in_browser,
            "inside": self.in_browser,
        }


async def test_screen_click_converts_normalized_coordinates(audit_path):
    desktop = FakeDesktop()
    gk = Gatekeeper(ScreenBrowser(), desktop=desktop, audit_path=audit_path)

    result = await gk.submit("r", "screen_click", {"x": 500, "y": 500})

    assert result["status"] == "done"
    assert desktop.ops == [
        ("click", {"x": 720, "y": 450, "button": "left", "clicks": 1})
    ]


async def test_screen_click_on_payment_button_is_never_executed(audit_path):
    desktop = FakeDesktop()
    browser = ScreenBrowser(target="Buy now")
    gk = Gatekeeper(browser, desktop=desktop, audit_path=audit_path)

    result = await gk.submit("r", "screen_click", {"x": 400, "y": 300})

    assert result["status"] == "denied"
    assert desktop.ops == []
    assert browser.asked_point == (576, 270)  # policy looked at the pixel to be clicked


async def test_screen_input_outside_the_browser_waits_for_approval(audit_path):
    desktop = FakeDesktop()
    gk = Gatekeeper(
        ScreenBrowser(in_browser=False), desktop=desktop, audit_path=audit_path
    )

    pending = await gk.submit("r", "screen_click", {"x": 500, "y": 500})
    assert pending["status"] == "needs_approval"
    assert desktop.ops == []

    done = await gk.resolve(pending["approval_id"], approve=True, channel="voice")
    assert done["status"] == "done"
    assert desktop.ops == [
        ("click", {"x": 720, "y": 450, "button": "left", "clicks": 1})
    ]


async def test_closing_a_window_waits_for_approval(audit_path):
    desktop = FakeDesktop()
    gk = Gatekeeper(ScreenBrowser(), desktop=desktop, audit_path=audit_path)

    pending = await gk.submit("r", "close_window", {"title": "Book1 - Excel"})

    assert pending["status"] == "needs_approval"
    assert pending["summary"] == "close the window 'Book1 - Excel'"
    assert desktop.ops == []


async def test_files_are_found_and_opened_but_programs_never_run(audit_path):
    desktop = FakeDesktop()
    gk = Gatekeeper(ScreenBrowser(), desktop=desktop, audit_path=audit_path)

    found = await gk.submit(
        "r", "find_files", {"query": "acme proposal", "kind": "word"}
    )
    opened = await gk.submit("r", "open_file", {"path": r"F:\Work\Acme proposal.docx"})
    blocked = await gk.submit(
        "r", "open_file", {"path": r"C:\Users\me\Downloads\setup.exe"}
    )

    assert found["status"] == opened["status"] == "done"
    assert blocked["status"] == "denied"
    assert desktop.ops == [
        ("find_files", {"query": "acme proposal", "kind": "word"}),
        ("open_file", {"path": r"F:\Work\Acme proposal.docx"}),
    ]


async def test_screen_keys_and_typing_go_to_the_desktop(audit_path):
    desktop = FakeDesktop()
    gk = Gatekeeper(ScreenBrowser(), desktop=desktop, audit_path=audit_path)

    await gk.submit("r", "screen_type", {"text": "你好 world"})
    await gk.submit("r", "screen_key", {"keys": "ctrl+t"})
    await gk.submit("r", "screen_key", {"keys": "Enter"})

    assert desktop.ops == [
        ("type", {"text": "你好 world"}),
        ("hotkey", {"keys": ["ctrl", "t"]}),
        ("press", {"key": "enter"}),
    ]


async def test_desktop_actions_fail_cleanly_without_desktop_control(audit_path):
    gk = Gatekeeper(FakeBrowser(), audit_path=audit_path)

    result = await gk.submit("r", "screen_click", {"x": 1, "y": 1})

    assert result["status"] == "error"


async def test_screenshot_comes_from_the_desktop(audit_path):
    gk = Gatekeeper(ScreenBrowser(), desktop=FakeDesktop(), audit_path=audit_path)
    assert await gk.screenshot() == b"\x89PNG fake"


class FlakyBrowser(FakeBrowser):
    """First call fails like a browser window the user just closed; the retry succeeds."""

    def __init__(self):
        super().__init__()
        self.failures = 1

    async def close_tab(self):
        if self.failures:
            self.failures -= 1
            raise RuntimeError("Target page, context or browser has been closed")
        self.calls.append(("close_tab",))
        return {"closed": True}


async def test_closed_browser_window_is_retried(audit_path):
    browser = FlakyBrowser()
    gk = Gatekeeper(browser, audit_path=audit_path)

    result = await gk.submit("r", "close_tab", {})

    assert result["status"] == "done"
    assert browser.calls == [("close_tab",)]


async def test_unexpected_browser_errors_are_reported_not_raised(audit_path):
    browser = FlakyBrowser()
    browser.failures = 5
    gk = Gatekeeper(browser, audit_path=audit_path)

    result = await gk.submit("r", "close_tab", {})

    assert result["status"] == "error"


# --- Office ---------------------------------------------------------------------


class FakeOffice:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def run(self, action, args):
        self.calls.append((action, args))
        return {"ok": True}


async def test_office_actions_go_to_office_and_saving_asks(audit_path):
    office = FakeOffice()
    gk = Gatekeeper(FakeBrowser(), office=office, audit_path=audit_path)

    edit = await gk.submit(
        "r", "ppt_edit", {"slide": 2, "find": "100", "replace_with": "1000"}
    )
    save = await gk.submit("r", "office_save", {"app": "powerpoint"})

    assert edit["status"] == "done"
    assert save["status"] == "needs_approval"
    assert office.calls == [
        ("ppt_edit", {"slide": 2, "find": "100", "replace_with": "1000"})
    ]


async def test_office_actions_fail_cleanly_without_office(audit_path):
    gk = Gatekeeper(FakeBrowser(), audit_path=audit_path)
    assert (await gk.submit("r", "office_read", {"app": "word"}))["status"] == "error"


# --- Email --------------------------------------------------------------------


class FakeEmailer:
    def __init__(self, gmail_state: str = "ready") -> None:
        self.sent: list[dict] = []
        self.gmail = FakeGmail(gmail_state)

    async def send(self, to, subject, message, changes=None, attachments=None):
        self.sent.append({"to": to, "subject": subject, "attachments": attachments})
        return {"sent": True}


DECK = {"to": ["jojo@client.example"], "subject": "Deck", "message": "Updated."}


async def test_every_email_is_asked_and_shows_who_it_goes_to(audit_path):
    emailer = FakeEmailer()
    gk = Gatekeeper(FakeBrowser(), emailer=emailer, audit_path=audit_path)

    first = await gk.submit("c", "send_email", DECK)
    await gk.resolve(first["approval_id"], approve=True, channel="voice")
    second = await gk.submit("c", "send_email", {**DECK, "subject": "Deck v2"})

    assert "jojo@client.example" in first["summary"]
    # The call's earlier approval does not cover another email
    assert second["status"] == "needs_approval"
    assert emailer.sent == [
        {"to": ["jojo@client.example"], "subject": "Deck", "attachments": []}
    ]


async def test_an_email_needs_real_recipients_and_never_attaches_programs(audit_path):
    gk = Gatekeeper(FakeBrowser(), emailer=FakeEmailer(), audit_path=audit_path)

    nobody = await gk.submit("c", "send_email", {**DECK, "to": []})
    a_name = await gk.submit("c", "send_email", {**DECK, "to": ["Ms Tan"]})
    program = await gk.submit(
        "c", "send_email", {**DECK, "attachments": [r"C:\x\setup.exe"]}
    )

    assert nobody["status"] == "denied" and "Ask the user" in nobody["reason"]
    assert a_name["status"] == "denied"
    assert program["status"] == "denied"


async def test_email_without_settings_fails_cleanly(audit_path):
    gk = Gatekeeper(FakeBrowser(), audit_path=audit_path)
    result = await gk.submit("c", "send_email", DECK)
    assert result["status"] == "error"


async def test_email_before_gmail_is_signed_in_says_where_to_sign_in(audit_path):
    for state in ("closed", "not_open", "signed_out"):
        gk = Gatekeeper(
            FakeBrowser(), emailer=FakeEmailer(state), audit_path=audit_path
        )
        result = await gk.submit("c", "send_email", DECK)
        assert (
            result["status"] == "error"
            and "Gmail in Chrome or Edge" in result["reason"]
        )
        assert gk.pending() == []  # never asked to approve what cannot be sent


class SavedOffice:
    """Reports an open PowerPoint file, saved or not."""

    def __init__(self, saved: bool) -> None:
        self.saved = saved

    async def run(self, action, args):
        assert action == "office_path"
        return {"path": r"C:\Docs\ACME_Sales_Pitch.pptx", "saved": self.saved}


async def _send_deck(gk):
    first = await gk.submit(
        "c",
        "send_email",
        {**DECK, "attach_open": ["powerpoint"]},
    )
    return await gk.resolve(first["approval_id"], approve=True, channel="web")


async def test_the_open_document_is_attached_once_saved(audit_path):
    emailer = FakeEmailer()
    gk = Gatekeeper(
        FakeBrowser(),
        office=SavedOffice(saved=True),
        emailer=emailer,
        audit_path=audit_path,
    )

    assert (await _send_deck(gk))["status"] == "done"
    assert emailer.sent == [
        {
            "to": ["jojo@client.example"],
            "subject": "Deck",
            "attachments": [r"C:\Docs\ACME_Sales_Pitch.pptx"],
        }
    ]


async def test_unsaved_changes_are_never_emailed_without_saving(audit_path):
    emailer = FakeEmailer()
    gk = Gatekeeper(
        FakeBrowser(),
        office=SavedOffice(saved=False),
        emailer=emailer,
        audit_path=audit_path,
    )

    result = await _send_deck(gk)

    assert result["status"] == "error" and "unsaved changes" in result["reason"]
    assert emailer.sent == []


async def test_finding_the_gmail_tab_is_allowed_without_asking(tmp_path):
    from policy import ALLOW, PageContext, decide

    assert decide("find_browser_tab", {"text": "Gmail"}, PageContext()).verdict == ALLOW


def test_opening_an_email_row_is_allowed_without_asking():
    from policy import ALLOW, PageContext, decide

    assert (
        decide("open_browser_item", {"text": "unread"}, PageContext()).verdict == ALLOW
    )


def test_reading_a_browser_page_is_allowed_without_asking():
    from policy import ALLOW, PageContext, decide

    assert (
        decide("read_browser_window", {"text": "Gmail"}, PageContext()).verdict == ALLOW
    )


def test_every_approval_is_spoken():
    from tools import approval_reminder

    assert approval_reminder("save Q-00002 as Excel and PDF") == (
        "Please approve: save Q-00002 as Excel and PDF. Tap Approve on screen, or say yes."
    )
    assert (
        approval_reminder("")
        == "Please approve: this step. Tap Approve on screen, or say yes."
    )


# --- Settings page and Gmail (HTTP) ------------------------------------------


@pytest.fixture
async def http(gmail, tmp_path, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer

    from emailer import Emailer
    from gatekeeper import create_app
    from settings import FIELDS, Settings

    for env in FIELDS.values():
        monkeypatch.setenv(env, "")
        monkeypatch.delenv(env)
    gk = Gatekeeper(
        FakeBrowser(), emailer=Emailer(gmail), audit_path=tmp_path / "a.jsonl"
    )
    app = create_app(gk, "secret", Settings(tmp_path / "settings.json"))
    async with TestClient(TestServer(app)) as client:
        yield client


TOKEN = {"X-Gatekeeper-Token": "secret"}


async def test_settings_and_gmail_need_the_token(http):
    for path in ("/v1/settings", "/v1/gmail"):
        assert (await http.get(path)).status == 401
    assert (await http.post("/v1/gmail/open")).status == 401


async def test_the_settings_page_reads_and_saves(http):
    saved = await (
        await http.post("/v1/settings", json={"voice": "robot"}, headers=TOKEN)
    ).json()
    assert saved == {
        "saved": False,
        "errors": {"voice": "Choose one of the listed voices."},
    }

    saved = await (
        await http.post("/v1/settings", json={"voice": "cedar"}, headers=TOKEN)
    ).json()
    shown = await (await http.get("/v1/settings", headers=TOKEN)).json()
    assert saved["saved"] and shown["values"]["voice"] == "cedar"


async def test_gmail_standby_status_and_open(http, gmail):
    gmail.state = "not_open"
    assert await (await http.get("/v1/gmail", headers=TOKEN)).json() == {
        "state": "not_open",
        "email": "",
    }
    opened = await (await http.post("/v1/gmail/open", headers=TOKEN)).json()
    assert gmail.opened == 1 and opened["state"] == "not_open"


async def test_a_test_email_from_settings(http, gmail):
    sent = await (
        await http.post("/v1/gmail/test", json={"to": "me@home.example"}, headers=TOKEN)
    ).json()
    bad = await (
        await http.post("/v1/gmail/test", json={"to": "nobody"}, headers=TOKEN)
    ).json()
    assert sent["sent"] and gmail.sent[0]["to"] == ["me@home.example"]
    assert bad == {"sent": False, "reason": "'nobody' is not an email address."}


async def test_the_panel_can_find_the_call_to_mirror(http):
    async def live():
        return await (await http.get("/v1/calls", headers=TOKEN)).json()

    assert (await http.get("/v1/calls")).status == 401
    assert await live() == {"room": None}

    await http.post("/v1/sessions/call-1/start", headers=TOKEN)
    await http.post("/v1/sessions/call-1/start", headers=TOKEN)  # reported twice
    assert await live() == {"room": "call-1"}
    await http.post("/v1/sessions/call-2/start", headers=TOKEN)
    assert await live() == {"room": "call-2"}  # the latest

    await http.post("/v1/sessions/call-2/end", headers=TOKEN)
    assert await live() == {"room": "call-1"}
    await http.post("/v1/sessions/call-1/end", headers=TOKEN)
    assert await live() == {"room": None}


async def test_gmail_health_for_the_settings_bar(http, gmail):
    assert (await http.get("/v1/gmail/health")).status == 401
    health = await (await http.get("/v1/gmail/health", headers=TOKEN)).json()
    assert health["connected"] and health["can_send"]
    gmail.state = "signed_out"
    health = await (await http.get("/v1/gmail/health", headers=TOKEN)).json()
    assert not health["connected"] and health["accounts"] == []


# --- Gmail is looked for, never opened -----------------------------------------


class GmailTabs:
    def __init__(self, found: bool) -> None:
        self.found = found
        self.looked_for: list[str] = []

    async def find_browser_tab(self, text: str) -> dict:
        self.looked_for.append(text)
        return {"found": self.found, "showing": {"browser": "msedge", "tab": "Gmail"}}


@pytest.mark.parametrize(
    ("action", "url"),
    [
        ("open_url", "https://mail.google.com"),
        ("open_url", "https://mail.google.com/mail/u/0/#inbox"),
        ("open_url", "https://gmail.com"),
        ("new_tab", "https://www.gmail.com/"),
    ],
)
async def test_asking_to_open_gmail_shows_the_open_tab_and_opens_nothing(
    audit_path, action, url
):
    browser = FakeBrowser()
    tabs = GmailTabs(found=True)
    gk = Gatekeeper(browser, desktop=tabs, audit_path=audit_path)

    result = await gk.submit("c", action, {"url": url})

    assert result["status"] == "done" and result["result"]["already_open"]
    assert tabs.looked_for == ["Gmail"]
    assert browser.calls == []  # the browser was not touched


async def test_gmail_open_nowhere_is_reported_and_no_browser_opens(audit_path):
    browser = FakeBrowser()
    gk = Gatekeeper(browser, desktop=GmailTabs(found=False), audit_path=audit_path)

    result = await gk.submit("c", "open_url", {"url": "https://mail.google.com"})

    assert result["status"] == "error" and "no browser was opened" in result["reason"]
    assert browser.calls == []


async def test_other_websites_still_open(audit_path):
    browser = FakeBrowser()
    tabs = GmailTabs(found=True)
    gk = Gatekeeper(browser, desktop=tabs, audit_path=audit_path)

    await gk.submit("c", "open_url", {"url": "https://www.google.com"})

    assert tabs.looked_for == []
    assert browser.calls  # opened as usual
