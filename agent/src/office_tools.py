"""Word, Excel and PowerPoint tools for the agent (direct, not by clicking the screen).

Every action goes through the gatekeeper, which runs it with office.py: Protected
View ("Enable Editing") is left automatically, the document is scrolled to the
part being changed, and edits are highlighted. Results come back as text, so no
screenshots are needed: much faster than screen control.
"""

from __future__ import annotations

import contextlib
import json
from typing import TypedDict

from livekit.agents import RunContext, function_tool, get_job_context

import quotation
from tools import BrowserTools

# Must match the web app's components/app/notifications.tsx
NOTIFY_TOPIC = "hireace.notify"


class QuoteItem(TypedDict, total=False):
    model: str  # from price_list
    quantity: int
    unit_price: float  # only when the user gave a different price
    description: str  # only for a product that is not in the price list


class OfficeTools:
    def __init__(self, browser_tools: BrowserTools) -> None:
        self._browser_tools = browser_tools

    @property
    def tools(self) -> list:
        return [
            self.office_read,
            self.office_go_to,
            self.word_edit,
            self.excel_set_cells,
            self.ppt_edit,
            self.office_save,
            self.send_email,
            self.price_list,
            self.make_quotation,
            self.save_quotation,
            self.send_quotation,
        ]

    async def _run(self, context: RunContext, action: str, args: dict):
        return await self._browser_tools._run(context, action, args)

    @function_tool()
    async def office_read(
        self, context: RunContext, app: str, sheet: str = "", document: str = ""
    ) -> dict:
        """Read an open Word document, Excel sheet or PowerPoint deck in one step.

        Word: numbered paragraphs. Excel: the sheet's cells as rows (with the range
        they cover) and the sheet names. PowerPoint: every slide with its shapes'
        names and text, and the current slide. Clicks "Enable Editing" if needed.

        Args:
            app: "word", "excel" or "powerpoint".
            sheet: Excel only: the sheet to read (default: the active one).
            document: Part of the file name when several files are open (default: the active one).
        """
        return await self._run(
            context, "office_read", {"app": app, "sheet": sheet, "document": document}
        )

    @function_tool()
    async def office_go_to(
        self, context: RunContext, app: str, target: str, document: str = ""
    ) -> dict:
        """Scroll the document to a place and select it, so the user sees what you mean.

        Use before changing something, and when the user asks to show a part.

        Args:
            app: "word", "excel" or "powerpoint".
            target: Word: a paragraph number. Excel: a cell or range, optionally with
                the sheet ("B5", "Sales!A1:D10"). PowerPoint: a slide number, optionally
                with a shape name after a colon ("3" or "3:Title 1").
            document: Part of the file name when several files are open.
        """
        return await self._run(
            context,
            "office_go_to",
            {"app": app, "target": target, "document": document},
        )

    @function_tool()
    async def word_edit(
        self,
        context: RunContext,
        find: str = "",
        replace_with: str = "",
        paragraph: int = 0,
        text: str = "",
        insert_after: bool = False,
        document: str = "",
    ) -> dict:
        """Change the open Word document. Changes are shown as tracked changes.

        Either replace text everywhere it appears (find + replace_with), or set a
        whole paragraph's text (paragraph + text), or add a new paragraph after one
        (paragraph + text + insert_after=True). Paragraph numbers come from office_read.

        Args:
            find: Exact text to replace (up to 255 characters).
            replace_with: The new text for find ("" deletes it).
            paragraph: Paragraph number to change, or to insert after.
            text: The paragraph's new text.
            insert_after: True to add text as a new paragraph after paragraph.
            document: Part of the file name when several files are open.
        """
        args = {
            "find": find,
            "replace_with": replace_with,
            "paragraph": paragraph,
            "text": text,
            "insert_after": insert_after,
            "document": document,
        }
        return await self._run(context, "word_edit", args)

    @function_tool()
    async def excel_set_cells(
        self,
        context: RunContext,
        cells: dict[str, str],
        sheet: str = "",
        document: str = "",
    ) -> dict:
        """Write values or formulas into Excel cells. Changed cells are filled yellow.

        Args:
            cells: Cell address to new value, for example {"B3": "120", "C3": "=B3*2"}.
            sheet: The sheet (default: the active one).
            document: Part of the file name when several files are open.
        """
        return await self._run(
            context,
            "excel_set_cells",
            {"cells": cells, "sheet": sheet, "document": document},
        )

    @function_tool()
    async def ppt_edit(
        self,
        context: RunContext,
        slide: int,
        shape: str = "",
        text: str = "",
        find: str = "",
        replace_with: str = "",
        document: str = "",
    ) -> dict:
        """Change text on a PowerPoint slide. Changed text is highlighted yellow.

        Either set a shape's whole text (shape + text, shape names from office_read)
        or replace text on the slide (find + replace_with). Goes to the slide first.

        Args:
            slide: The slide number.
            shape: The shape's name, for example "Title 1".
            text: The shape's new text.
            find: Exact text to replace on this slide.
            replace_with: The new text for find.
            document: Part of the file name when several files are open.
        """
        args = {
            "slide": slide,
            "shape": shape,
            "text": text,
            "find": find,
            "replace_with": replace_with,
            "document": document,
        }
        return await self._run(context, "ppt_edit", args)

    @function_tool()
    async def office_save(
        self, context: RunContext, app: str, document: str = ""
    ) -> dict:
        """Save the open Word, Excel or PowerPoint file (overwrites it on disk).

        Only when the user wants the changes saved.

        Args:
            app: "word", "excel" or "powerpoint".
            document: Part of the file name when several files are open.
        """
        return await self._run(
            context, "office_save", {"app": app, "document": document}
        )

    @function_tool()
    async def send_email(
        self,
        context: RunContext,
        to: list[str],
        subject: str,
        summary: str,
        changes: list[str] | None = None,
        attach_open: list[str] | None = None,
        attachments: list[str] | None = None,
    ) -> dict:
        """Email documents to the people the user names, from the Gmail already open
        in a browser.

        Write it for the person receiving it, not for the user: never "Sir". The
        greeting ("Hi,"), layout and sign-off are added for you. Save edited
        documents with office_save first. The user always approves it on screen.

        Args:
            to: The recipients' email addresses: the ones the user gave, or the
                sender of the email being answered, exactly as shown in it.
                Never guessed or made up: if the user did not say, ask them first.
            subject: A clear subject, e.g. "Updated Acme sales pitch deck".
            summary: One or two sentences on what is attached and why, e.g. "Please
                find the updated Acme sales pitch deck. The changes are highlighted."
            changes: What changed, one short line each with where, e.g.
                ["Slide 3: shortened the title", "Slide 10: updated the ROI figures"].
            attach_open: Attach the open, saved document of these apps: any of
                "word", "excel", "powerpoint". Use this for files you just edited.
            attachments: Full paths of other files to attach (from find_files).
        """
        args = {
            "to": to,
            "subject": subject,
            "message": summary,
            "changes": changes or [],
            "attach_open": attach_open or [],
            "attachments": attachments or [],
        }
        result = await self._run(context, "send_email", args)
        if isinstance(result, dict) and result.get("sent"):
            await _notify_app({"type": "email_sent", **result})
        return result

    @function_tool()
    async def price_list(self) -> dict:
        """The products the company sells, with model, description and unit price (SGD).

        Use it to match what a customer asks for to a model before make_quotation.
        """
        try:
            return {"currency": "SGD", "products": quotation.load_price_list()}
        except (OSError, ValueError, KeyError) as exc:
            return {"error": f"The price list could not be read: {exc}"}

    @function_tool()
    async def make_quotation(
        self,
        context: RunContext,
        customer: str,
        items: list[QuoteItem],
        shipping: float = 0.0,
        tax_rate: float = 0.0,
        contact: str = "",
        customer_email: str = "",
        address: list[str] | None = None,
        phone: str = "",
        discount: float = 0.0,
        notes: list[str] | None = None,
    ) -> dict:
        """Prepare the quotation draft: open the company template in Excel and fill it
        in on screen while the user watches. The draft stays open, unsaved, for the
        user to check; save_quotation saves it once they approve. Calling this again
        replaces the open draft (e.g. after a change).

        Gives it the next quote number and today's date and works out the totals.

        Args:
            customer: The customer's company, e.g. "Seaview Hotel, Harbourfront".
            items: One per product: {"model": model from price_list, "quantity": n};
                add "unit_price" only if the user gave another price. A product not in
                the price list: {"description": ..., "unit_price": ..., "quantity": n}.
            shipping: Shipping charge in SGD. 0 unless the user asks for one.
            tax_rate: Tax rate in percent. 0 unless the user asks for tax (e.g. 9 when
                they say "add 9% GST").
            contact: The person who asked, e.g. "Ms Tan".
            customer_email: The address the request came from.
            address: The customer's address lines from the email's signature, e.g.
                ["1 Harbour Road", "Example City",
                "Example Country 10000"]; only what the email gives, never invented.
            phone: The customer's phone number from the email, e.g. "60-12 345 6789".
            discount: Discount in SGD, only if the user asked for one.
            notes: Special notes, only if the user asks for some (normally empty).
        """
        args = {
            "customer": customer,
            "items": [dict(item) for item in items],
            "shipping": shipping,
            "tax_rate": tax_rate,
            "contact": contact,
            "customer_email": customer_email,
            "address": address or [],
            "phone": phone,
            "discount": discount,
            "notes": notes or [],
        }
        return await self._run(context, "make_quotation", args)

    @function_tool()
    async def save_quotation(self, context: RunContext, quote_number: str) -> dict:
        """Save the approved quotation draft, on screen: as a new Excel file, then as
        PDF; the PDF opens for the user to preview and the draft closes in Excel.

        The user always approves this first. Returns the PDF's path for send_quotation.

        Args:
            quote_number: The draft's number from make_quotation, e.g. "Q-00002".
        """
        return await self._run(
            context, "save_quotation", {"quote_number": quote_number}
        )

    @function_tool()
    async def send_quotation(
        self,
        context: RunContext,
        contact: str,
        customer_email: str,
        inquiry_subject: str,
        message: str,
        pdf: str,
    ) -> dict:
        """Email the quotation PDF (from save_quotation) as the reply to the inquiry.

        It goes to the customer who sent the inquiry, with the subject "Re: <inquiry
        subject>", from the Gmail already open in a browser. The user always approves
        it on screen first (the card shows the address). The greeting ("Dear
        <contact>,") and the sign-off are added for you.

        Args:
            contact: How to greet them, e.g. "Ms Tan".
            customer_email: The inquiry sender's address, exactly as shown next to
                their name in the open email (never from a window title or anywhere
                else).
            inquiry_subject: The inquiry email's subject, exactly as in the email, e.g.
                "Inquiry for office equipment — Seaview Hotel".
            message: Two or three short paragraphs for the customer: thanks for the
                enquiry, what the quotation covers and the total, your recommendation,
                and an offer to answer questions. Never "Sir".
            pdf: The quotation's PDF path from save_quotation.
        """
        args = {
            "to": customer_email,
            "contact": contact,
            "subject": inquiry_subject,
            "message": message,
            "attachments": [pdf],
        }
        result = await self._run(context, "send_quotation", args)
        if isinstance(result, dict) and result.get("sent"):
            await _notify_app({"type": "email_sent", **result})
        return result


async def _notify_app(event: dict) -> None:
    """Pop up a notice in the user's app (e.g. "Email sent" with a Gmail link)."""
    try:
        room = get_job_context().room
    except RuntimeError:
        return  # no call (tests, console)
    with contextlib.suppress(Exception):
        await room.local_participant.send_text(json.dumps(event), topic=NOTIFY_TOPIC)
