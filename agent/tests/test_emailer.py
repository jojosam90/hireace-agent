import pytest
from conftest import SENDER

from emailer import Emailer, EmailError, recipients


async def test_sends_a_proper_email_to_the_people_named(gmail, tmp_path, monkeypatch):
    monkeypatch.delenv("EMAIL_SIGNATURE", raising=False)
    doc = tmp_path / "ACME_Proposal.docx"
    doc.write_bytes(b"docx bytes")

    result = await Emailer(gmail).send(
        ["jojo@client.example"],
        "Proposal updated",
        "Please find the updated proposal.",
        changes=["Page 2: new prices"],
        attachments=[str(doc)],
    )

    [sent] = gmail.sent
    assert sent["to"] == ["jojo@client.example"]
    assert sent["subject"] == "Proposal updated"
    # Written for the recipient: greeting, summary, changes, attachment, sign-off
    assert sent["text"] == (
        "Hi,\n\nPlease find the updated proposal.\n\n"
        "What changed (highlighted in the file):\n- Page 2: new prices\n\n"
        "Attached: ACME_Proposal.docx\n\nBest regards,\nHireAce"
    )
    assert sent["attachments"] == [str(doc.resolve())]
    assert result["to"] == ["jojo@client.example"] and result["from"] == SENDER
    assert result["attachments"] == ["ACME_Proposal.docx"]
    # The sender's mailbox (Sent), through the account chooser
    assert result["gmail_link"].startswith(
        f"https://accounts.google.com/AccountChooser?Email={SENDER}&continue="
    )


async def test_the_signature_from_settings_counts_straight_away(gmail, monkeypatch):
    monkeypatch.setenv("EMAIL_SIGNATURE", "Jojo, Consap")
    await Emailer(gmail).send(["a@b.example"], "s", "m")
    assert gmail.sent[0]["text"].endswith("Best regards,\nJojo, Consap")


async def test_missing_attachment_is_an_error_before_sending(gmail):
    with pytest.raises(EmailError, match="Save the document first"):
        await Emailer(gmail).send(
            ["x@y.example"], "s", "m", attachments=[r"C:\nope\missing.docx"]
        )
    assert gmail.sent == []


async def test_a_test_email_checks_sending(gmail):
    result = await Emailer(gmail).send_test("me@home.example")
    assert result["sent"] and gmail.sent[0]["to"] == ["me@home.example"]


async def test_nothing_is_sent_until_gmail_is_signed_in(gmail):
    gmail.state = "signed_out"
    with pytest.raises(EmailError, match="Gmail in Chrome or Edge"):
        await Emailer(gmail).send(["a@b.example"], "s", "m")


def test_recipients_are_checked():
    assert recipients(["a@b.example", " c@d.example "]) == [
        "a@b.example",
        "c@d.example",
    ]
    assert recipients("a@b.example; A@B.example, c@d.example") == [
        "a@b.example",
        "c@d.example",
    ]
    with pytest.raises(EmailError, match="ask the user"):
        recipients([])
    with pytest.raises(EmailError, match="not an email address"):
        recipients(["Ms Tan"])
    with pytest.raises(EmailError, match="At most 10"):
        recipients([f"p{i}@x.example" for i in range(11)])
