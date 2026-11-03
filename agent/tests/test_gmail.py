"""GmailWindow in a real (headless) Chromium, against a stand-in for Gmail's pages
with the same markers gmail.py relies on."""

import json
import re
from urllib.parse import parse_qs, urlparse

import pytest

import gmail as gmail_module
from browser import BrowserManager
from gmail import GmailError, GmailWindow, signed_in_accounts

INBOX = "<title>Inbox (3) - sales@company.example - Gmail</title><p>Inbox</p>"
SIGNED_OUT = "<title>Gmail</title><p>Loading</p>"
COMPOSE = """<title>Compose</title>
<div g_editable="true" contenteditable="true" role="textbox"
     style="width:300px;height:100px;border:1px solid"></div>
<input type="file" multiple name="Filedata" style="display:none">
<div id="files"></div>
<script>
const params = new URLSearchParams(location.search);
const input = document.querySelector('input[type=file]');
input.addEventListener('change', () => {
  for (const f of input.files) {
    const chip = document.createElement('div');
    chip.textContent = f.name;
    document.getElementById('files').appendChild(chip);
  }
  const bar = document.createElement('div');
  bar.setAttribute('role', 'progressbar');
  bar.textContent = 'Uploading';
  document.body.appendChild(bar);
  setTimeout(() => bar.remove(), 300);
});
document.querySelector('[g_editable]').addEventListener('keydown', async (e) => {
  if (e.key !== 'Enter' || !e.ctrlKey) return;
  if (params.get('su') === 'FAIL') {
    const alert = document.createElement('div');
    alert.setAttribute('role', 'alertdialog');
    alert.textContent = 'The address "x" in the "To" field was not recognized.';
    document.body.appendChild(alert);
    return;
  }
  await fetch('/__sent', {method: 'POST', body: JSON.stringify({
    to: params.get('to'), su: params.get('su'), body: params.get('body'),
    files: [...input.files].map(f => f.name)})});
  document.querySelector('[g_editable]').remove();
});
</script>"""


@pytest.fixture
async def fake_gmail(monkeypatch):
    """HireAce's browser, with mail.google.com answered by the stand-in."""
    # Real Gmail sends the bare address on to the signed-in account's inbox (a
    # redirect the stand-in cannot fake): open that inbox directly
    monkeypatch.setattr(gmail_module, "GMAIL_URL", "https://mail.google.com/mail/u/0/")
    manager = BrowserManager(headless=True)
    state = {"inbox": INBOX, "sent": []}

    async def answer(route):
        request = route.request
        if request.method == "POST":
            state["sent"].append(json.loads(request.post_data))
            return await route.fulfill(body="ok")
        page = COMPOSE if "view=cm" in request.url else state["inbox"]
        return await route.fulfill(content_type="text/html", body=page)

    state["start"] = lambda: manager._context.route(
        re.compile(r"^https://mail\.google\.com/"), answer
    )
    yield manager, state
    await manager.close()


async def test_status_never_opens_the_browser(fake_gmail):
    manager, _ = fake_gmail
    assert await GmailWindow(manager).status() == {"state": "closed", "email": ""}
    assert not manager.running


async def test_gmail_on_standby_sends_through_its_compose_page(fake_gmail, tmp_path):
    manager, state = fake_gmail
    gmail = GmailWindow(manager)
    await manager.start()
    await state["start"]()
    assert (await gmail.status())["state"] == "not_open"

    assert await gmail.open() == {"state": "ready", "email": "sales@company.example"}
    quote = tmp_path / "Quotation Q-00002.pdf"
    quote.write_bytes(b"%PDF")
    sent = await gmail.send(
        ["tan@seaview.example", "ops@seaview.example"],
        "Re: Inquiry",
        "Dear Ms Tan,\n\nPlease find our quotation.",
        [str(quote)],
    )

    assert sent == {"from": "sales@company.example"}
    assert state["sent"] == [
        {
            "to": "tan@seaview.example,ops@seaview.example",
            "su": "Re: Inquiry",
            "body": "Dear Ms Tan,\n\nPlease find our quotation.",
            "files": ["Quotation Q-00002.pdf"],
        }
    ]
    # The compose tab is closed again; the user's Gmail tab is left as it was
    assert [p.url for p in manager.pages()] == ["https://mail.google.com/mail/u/0/"]


async def test_signed_out_gmail_sends_nothing(fake_gmail):
    manager, state = fake_gmail
    state["inbox"] = SIGNED_OUT
    gmail = GmailWindow(manager)
    await manager.start()
    await state["start"]()

    assert (await gmail.open())["state"] == "signed_out"
    with pytest.raises(GmailError, match="Gmail in Chrome or Edge"):
        await gmail.send(["a@b.example"], "s", "t", [])
    assert state["sent"] == []


async def test_gmails_own_error_is_passed_on(fake_gmail, monkeypatch):
    monkeypatch.setattr(gmail_module, "SEND_TIMEOUT_S", 2)
    manager, state = fake_gmail
    gmail = GmailWindow(manager)
    await manager.start()
    await state["start"]()
    await gmail.open()

    with pytest.raises(GmailError, match='"To" field was not recognized'):
        await gmail.send(["a@b.example"], "FAIL", "t", [])
    assert len(manager.pages()) == 1


async def test_open_in_gmail_shows_the_link_in_hireaces_browser(fake_gmail):
    manager, state = fake_gmail
    gmail = GmailWindow(manager)
    await manager.start()
    await state["start"]()

    link = "https://mail.google.com/mail/u/0/#search/in%3Asent"
    assert (await gmail.open(link))["state"] == "ready"
    assert manager.pages()[0].url == link
    with pytest.raises(GmailError, match="Only Gmail links"):
        await gmail.open("https://evil.example/mail")


def test_only_signed_in_gmail_tabs_count_in_any_browser():
    windows = [
        {
            "browser": "msedge",
            "tabs": [
                "Inbox (3) - Me.Name@Gmail.com - Gmail",
                "gmail login - Google Search",
                "Gmail",
                "Sign in - Google Accounts",
            ],
        },
        {
            "browser": "chrome",
            "tabs": ["Inbox - sales@company.example - Company Mail", "Example Domain"],
        },
        {"browser": "msedge", "tabs": ["Sent - me.name@gmail.com - Gmail"]},
        {"browser": "firefox", "tabs": []},
    ]
    assert signed_in_accounts(windows) == [
        {"browser": "Edge", "process": "msedge", "email": "me.name@gmail.com"},
        {"browser": "Chrome", "process": "chrome", "email": "sales@company.example"},
    ]


async def test_health_finds_gmail_in_other_browsers(fake_gmail, monkeypatch):
    manager, _ = fake_gmail
    calls = []

    def tabs():
        calls.append(1)
        return {
            "windows": [{"browser": "msedge", "tabs": ["Inbox - a@b.example - Gmail"]}],
            "selected": None,
        }

    monkeypatch.setattr(gmail_module, "browser_tabs", tabs)
    gmail = GmailWindow(manager)

    health = await gmail.health()
    assert health == {
        "checked": True,
        "connected": True,
        "accounts": [{"browser": "Edge", "email": "a@b.example"}],
        "can_send": True,
    }
    await gmail.health()
    assert len(calls) == 1  # read again only after a while: it costs CPU


async def test_health_says_so_when_the_tabs_cannot_be_read(fake_gmail, monkeypatch):
    def broken():
        raise OSError("no")

    monkeypatch.setattr(gmail_module, "browser_tabs", broken)
    manager, _ = fake_gmail
    health = await GmailWindow(manager).health()
    assert not health["checked"] and not health["connected"]


def edge_with_gmail():
    return {
        "windows": [{"browser": "msedge", "tabs": ["Inbox - me@gmail.com - Gmail"]}],
        "selected": None,
    }


async def test_sends_from_the_gmail_already_open_in_another_browser(
    fake_gmail, monkeypatch, tmp_path
):
    manager, _ = fake_gmail
    jobs = []

    def send(job):
        jobs.append(job)
        return {"sent": True}

    monkeypatch.setattr(gmail_module, "browser_tabs", edge_with_gmail)
    monkeypatch.setattr(gmail_module, "send_in_browser", send)

    sent = await GmailWindow(manager).send(
        ["a@b.example"], "Re: Inquiry", "Dear Ms Tan,\n\nHello & thanks", [r"C:\q.pdf"]
    )

    assert sent == {"from": "me@gmail.com"}
    [job] = jobs
    assert job["browser"] == "msedge" and job["email"] == "me@gmail.com"
    assert job["subject"] == "Re: Inquiry" and job["files"] == [r"C:\q.pdf"]
    query = parse_qs(urlparse(job["url"]).query)
    assert query["authuser"] == ["me@gmail.com"]
    assert query["to"] == ["a@b.example"] and query["su"] == ["Re: Inquiry"]
    assert query["body"] == ["Dear Ms Tan,\n\nHello & thanks"]
    assert query["view"] == ["cm"] and query["hl"] == ["en"]
    assert not manager.running  # HireAce's own browser was not needed


async def test_a_send_that_fails_in_the_browser_says_why(fake_gmail, monkeypatch):
    manager, _ = fake_gmail
    monkeypatch.setattr(gmail_module, "browser_tabs", edge_with_gmail)
    monkeypatch.setattr(
        gmail_module,
        "send_in_browser",
        lambda job: {"sent": False, "reason": "Gmail opened in another account."},
    )
    with pytest.raises(GmailError, match="another account"):
        await GmailWindow(manager).send(["a@b.example"], "s", "t", [])


async def test_a_message_too_long_for_the_compose_address_is_refused(
    fake_gmail, monkeypatch
):
    manager, _ = fake_gmail
    monkeypatch.setattr(gmail_module, "browser_tabs", edge_with_gmail)
    with pytest.raises(GmailError, match="too long"):
        await GmailWindow(manager).send(["a@b.example"], "s", "t" * 9000, [])


async def test_gmail_in_a_minimized_browser_still_counts(fake_gmail, monkeypatch):
    manager, _ = fake_gmail
    title = "Inbox (1) - me@gmail.com - Gmail and 2 more pages - Microsoft Edge"
    monkeypatch.setattr(
        gmail_module,
        "browser_tabs",
        lambda: {
            "windows": [{"browser": "msedge", "window": 7, "title": title, "tabs": []}],
            "selected": None,
        },
    )
    assert (await GmailWindow(manager).health())["accounts"] == [
        {"browser": "Edge", "email": "me@gmail.com"}
    ]


async def test_a_minimized_window_keeps_its_last_known_gmail_tab(
    fake_gmail, monkeypatch
):
    manager, _ = fake_gmail
    gmail = GmailWindow(manager)
    tabs = ["Other page", "Inbox - me@gmail.com - Gmail"]

    def windows():
        return {
            "windows": [
                {"browser": "msedge", "window": 7, "title": "Other page", "tabs": tabs}
            ],
            "selected": None,
        }

    monkeypatch.setattr(gmail_module, "browser_tabs", windows)
    assert len(await gmail._open_accounts()) == 1
    tabs = []  # minimized: Windows now reports none
    assert len(await gmail._open_accounts()) == 1

    monkeypatch.setattr(
        gmail_module, "browser_tabs", lambda: {"windows": [], "selected": None}
    )
    assert await gmail._open_accounts() == []  # closed: forgotten


# --- Minimized browsers -----------------------------------------------------------


GMAIL_TAB = "Inbox (3) - someone@example.com - Gmail"


def _gmail_window(monkeypatch, windows, minimized, read):
    """A GmailWindow seeing these windows; read: what an off-screen look finds."""
    import gmail as gmail_module

    looks = []

    def look(handles):
        looks.append(list(handles))
        return read(handles)

    monkeypatch.setattr(gmail_module, "browser_tabs", lambda: {"windows": windows(), "selected": None})
    monkeypatch.setattr(gmail_module, "is_minimized", lambda handle: handle in minimized)
    monkeypatch.setattr(gmail_module, "read_minimized_tabs", look)
    return gmail_module.GmailWindow(None), looks


async def test_gmail_in_a_background_tab_of_a_minimized_browser_is_found_by_itself(monkeypatch):
    """The browser was minimized before HireAce started, with another tab in front."""
    window, looks = _gmail_window(
        monkeypatch,
        lambda: [{"browser": "msedge", "window": 1, "title": "Other - Edge", "tabs": ["Primary"]}],
        {1},
        lambda handles: {1: ["Other", GMAIL_TAB]},
    )

    accounts = await window._open_accounts()

    assert [a["email"] for a in accounts] == ["someone@example.com"]
    assert looks == [[1]]
    assert [a["email"] for a in await window._open_accounts()] == ["someone@example.com"]
    assert looks == [[1]]  # read once: not every 10 seconds


async def test_a_minimized_window_is_only_looked_at_a_few_times(monkeypatch):
    import gmail as gmail_module

    window, looks = _gmail_window(
        monkeypatch,
        lambda: [{"browser": "chrome", "window": 2, "title": "App", "tabs": []}],
        {2},
        lambda handles: {},
    )
    for _ in range(gmail_module.MAX_PEEKS + 3):
        assert await window._open_accounts() == []
    assert len(looks) == gmail_module.MAX_PEEKS


async def test_tabs_seen_on_screen_are_not_looked_for_again_when_minimized(monkeypatch):
    minimized = set()
    window, looks = _gmail_window(
        monkeypatch,
        lambda: [{"browser": "chrome", "window": 3, "title": "T", "tabs": [] if minimized else [GMAIL_TAB]}],
        minimized,
        lambda handles: {},
    )
    assert len(await window._open_accounts()) == 1
    minimized.add(3)
    assert len(await window._open_accounts()) == 1
    assert looks == []


async def test_page_items_of_a_minimized_browser_never_replace_its_tabs(monkeypatch):
    minimized = set()
    tabs = [GMAIL_TAB]
    window, _ = _gmail_window(
        monkeypatch,
        lambda: [{"browser": "chrome", "window": 4, "title": "T", "tabs": list(tabs)}],
        minimized,
        lambda handles: {},
    )
    await window._open_accounts()
    minimized.add(4)
    tabs[:] = ["Primary", "Promotions"]
    assert len(await window._open_accounts()) == 1


async def test_hireace_own_minimized_panel_is_left_alone(monkeypatch):
    window, looks = _gmail_window(
        monkeypatch,
        lambda: [{"browser": "chrome", "window": 5, "title": "HireAce", "tabs": []}],
        {5},
        lambda handles: {},
    )
    await window._open_accounts()
    assert looks == []


async def test_a_gmail_opened_while_checking_shows_at_the_next_check(monkeypatch):
    tabs = ["Other"]
    window, _ = _gmail_window(
        monkeypatch,
        lambda: [{"browser": "chrome", "window": 6, "title": "T", "tabs": tabs}],
        set(),
        lambda handles: {},
    )
    assert await window._open_accounts() == []
    tabs.append(GMAIL_TAB)
    assert len(await window._open_accounts()) == 1
