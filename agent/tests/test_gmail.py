"""GmailWindow in a real (headless) Chromium, against a stand-in for Gmail's pages
with the same markers gmail.py relies on."""

import json
import re

import pytest

import gmail as gmail_module
from browser import BrowserManager
from gmail import GmailError, GmailWindow

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
    with pytest.raises(GmailError, match="Open Gmail and sign in"):
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
