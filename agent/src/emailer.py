"""Send email with documents attached, from the Gmail signed in in HireAce's browser
(gmail.py).

Only the gatekeeper uses this, and only after the user approved that very email. A
document goes to the people the user named. A quotation goes back to the customer
who asked for it, with the inquiry's subject. Nobody gets a copy.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import quote

from gmail import GmailError, GmailWindow

MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024  # Gmail's limit for attachments
MAX_RECIPIENTS = 10
EMAIL_ADDRESS = re.compile(r"[^@\s,;<>\"]+@[^@\s,;<>\"]+\.[A-Za-z]{2,}")


class EmailError(Exception):
    """A user-facing email failure."""


def recipients(to) -> list[str]:
    """The addresses in ``to`` (a list, or one string split by commas or
    semicolons), each checked, without repeats."""
    items = to if isinstance(to, list) else re.split(r"[,;]", str(to or ""))
    found: list[str] = []
    for item in items:
        address = str(item).strip()
        if not address:
            continue
        if not EMAIL_ADDRESS.fullmatch(address):
            raise EmailError(f"{address!r} is not an email address.")
        if address.lower() not in (a.lower() for a in found):
            found.append(address)
    if not found:
        raise EmailError("Nobody to send it to: ask the user for the email address.")
    if len(found) > MAX_RECIPIENTS:
        raise EmailError(f"At most {MAX_RECIPIENTS} recipients.")
    return found


class Emailer:
    def __init__(self, gmail: GmailWindow) -> None:
        self.gmail = gmail

    # Read on every email, so a change in Settings counts straight away
    @property
    def signature(self) -> str:
        return os.environ.get("EMAIL_SIGNATURE", "").strip() or "HireAce"

    @property
    def sales_signature(self) -> str:
        return os.environ.get("QUOTE_SIGNATURE", "").strip() or "Sales Team"

    async def send(
        self,
        to,
        subject: str,
        message: str,
        changes: list[str] | None = None,
        attachments: list[str] | None = None,
    ) -> dict:
        to = recipients(to)
        files = _check_files(attachments)
        names = [Path(f).name for f in files]
        text = compose_text(message, changes or [], names, self.signature)
        return await self._send(to, subject, text, files)

    async def send_quotation(
        self,
        to: str,
        contact: str,
        subject: str,
        message: str,
        attachments: list[str],
    ) -> dict:
        """To the customer who sent the inquiry (``to``), subject "Re: <inquiry>"."""
        to_list = recipients([to])
        files = _check_files(attachments)
        names = [Path(f).name for f in files]
        greeting = (
            f"Dear {contact.strip()}," if contact.strip() else "Dear Sir or Madam,"
        )
        text = compose_text(message, [], names, self.sales_signature, greeting)
        return await self._send(to_list, subject, text, files)

    async def send_test(self, to: str) -> dict:
        """A short email from Settings, to check sending works."""
        text = (
            "This is a test email from HireAce. Sending email works.\n\n"
            f"Best regards,\n{self.signature}"
        )
        return await self._send(recipients(to), "HireAce test email", text, [])

    async def _send(
        self, to: list[str], subject: str, text: str, files: list[str]
    ) -> dict:
        try:
            sent = await self.gmail.send(to, subject, text, files)
        except GmailError as exc:
            raise EmailError(str(exc)) from exc
        return {
            "sent": True,
            "from": sent["from"],
            "to": to,
            "subject": subject,
            "attachments": [Path(f).name for f in files],
            # In the sender's mailbox (Sent), which is the user's own
            "gmail_link": gmail_link(sent["from"], subject),
        }


def _check_files(attachments: list[str] | None) -> list[str]:
    files = []
    total = 0
    for path in attachments or []:
        file = Path(path)
        if not file.is_file():
            raise EmailError(
                f"{path!r} is not a file. Save the document first and attach its path."
            )
        total += file.stat().st_size
        if total > MAX_ATTACHMENT_BYTES:
            raise EmailError("The attachments are too large to email (25 MB at most).")
        files.append(str(file.resolve()))
    return files


# --- The email itself ---------------------------------------------------------------
# The agent writes the summary and the list of changes; the greeting, layout and
# sign-off are fixed here so every email looks the same and reads well.


def compose_text(
    message: str,
    changes: list[str],
    attachments: list[str],
    signature: str,
    greeting: str = "Hi,",
) -> str:
    parts = [greeting, message.strip()]
    if changes:
        bullets = "\n".join(f"- {c}" for c in changes)
        parts.append(f"What changed (highlighted in the file):\n{bullets}")
    if attachments:
        parts.append("Attached: " + ", ".join(attachments))
    parts.append(f"Best regards,\n{signature}")
    return "\n\n".join(parts)


def gmail_link(mailbox: str, subject: str) -> str:
    """Opens the sender's mailbox in Gmail, searching for this email.

    Through Google's account chooser: Gmail on its own quietly opens whichever
    account is signed in instead (the email is not there). If the mailbox is
    signed in this goes straight through; if not, Google asks to sign in to it.
    """
    search = quote(f'in:sent subject:"{subject}"', safe="")
    inbox = f"https://mail.google.com/mail/?authuser={quote(mailbox, safe='@')}#search/{search}"
    return (
        "https://accounts.google.com/AccountChooser"
        f"?Email={quote(mailbox, safe='@')}&continue={quote(inbox, safe='')}"
    )
