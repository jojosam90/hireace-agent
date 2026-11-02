import datetime
from pathlib import Path

import pytest
from conftest import FakeGmail
from test_gatekeeper import FakeBrowser

import quotation
from emailer import Emailer, EmailError
from gatekeeper import Gatekeeper
from policy import ALLOW, ASK, DENY, PageContext, decide
from quotation import WIDE_COLON, QuoteError, build_quote

# Made-up products and prices (the company's own list stays on its PC)
EXAMPLE_PRICES = Path(__file__).parent.parent / "price_list.example.json"

SEAVIEW_ITEMS = [
    {"model": "AC-GW-100", "quantity": 150},
    {"model": "AC-SW-4", "quantity": 450},
    {"model": "AC-AC-27", "quantity": 150},
    {"model": "AC-PS-24", "quantity": 450},
]


def seaview(**overrides):
    args = {
        "customer": "Seaview Hotel, Harbourfront",
        "contact": "Ms Tan",
        "customer_email": "tan@seaview.example",
        "address": [
            "1 Harbour Road",
            "Example City",
            "Example Country 10000",
        ],
        "phone": "60-12 345 6789",
        "items": SEAVIEW_ITEMS,
        "shipping": 1800,
        "tax_rate": 9,
        "number": 2,
        "date": datetime.date(2026, 10, 29),
        "price_list": quotation.load_price_list(EXAMPLE_PRICES),
    }
    return build_quote(**{**args, **overrides})


def test_the_seaview_request_is_priced_from_the_price_list():
    quote = seaview()

    assert [line.amount for line in quote.lines] == [9000.0, 22500.0, 30000.0, 45000.0]
    assert quote.subtotal == 106500.0
    # Tax on goods and shipping (as GST is charged)
    assert quote.tax == round((106500 + 1800) * 0.09, 2)
    assert quote.total == round(106500 + 1800 + quote.tax, 2)
    # Written as in the company's sample, full-width colons included
    assert quote.lines[0].text.splitlines() == [
        f"Item{WIDE_COLON} Gateway",
        f"Description{WIDE_COLON}System gateway supporting BLE / Wi-Fi",
        "Brand: Acme",
        "Model: AC-GW-100",
    ]


def test_header_fields_and_file_name():
    quote = seaview()

    assert quote.quote_no == "00002"
    assert quote.customer_id == "SH00002"
    assert quote.valid_until == datetime.date(2026, 11, 28)
    assert quote.file_stem == "Quotation Q-00002 Seaview Hotel"
    # As in the company's sample: company, address, phone
    assert quote.billed_to() == [
        "Seaview Hotel, Harbourfront",
        "1 Harbour Road",
        "Example City",
        "Example Country 10000",
        "60-12 345 6789",
    ]
    assert quote.full_notes() == ""  # the sample's notes box is empty
    assert quotation._date(quote.date) == "10/29/2026"  # the template's MM/DD/YYYY


def test_billed_to_fits_the_five_lines():
    long = seaview(address=["Street 1", "Area 2", "City 3", "Country 4"])
    assert long.billed_to()[-2:] == ["City 3, Country 4", "60-12 345 6789"]
    assert len(long.billed_to()) == 5
    no_address = seaview(address=[], phone="")
    assert no_address.billed_to() == [
        "Seaview Hotel, Harbourfront",
        "Attn: Ms Tan",
    ]


def test_a_price_the_user_gave_and_a_product_not_on_the_list():
    quote = seaview(
        items=[
            {"model": "ac-gw-100", "quantity": 10, "unit_price": 55},
            {
                "description": "Installation and commissioning",
                "unit_price": 2000,
                "quantity": 1,
            },
        ],
        shipping=0,
        tax_rate=0,
    )
    assert [(line.unit_price, line.quantity) for line in quote.lines] == [
        (55.0, 10),
        (2000.0, 1),
    ]
    assert quote.total == 2550.0


def test_unknown_products_and_bad_numbers_are_explained():
    with pytest.raises(QuoteError, match=r"not in the price list.*AC-GW-100"):
        seaview(items=[{"model": "XYZ-1", "quantity": 5}])
    with pytest.raises(QuoteError, match="quantity"):
        seaview(items=[{"model": "AC-AC-27", "quantity": 0}])
    with pytest.raises(QuoteError, match="negative"):
        seaview(shipping=-1)


def test_numbers_continue_from_the_quotations_already_made(tmp_path):
    assert quotation.next_number(tmp_path) == 1
    (tmp_path / "Quotation Q-00007 Seaview Hotel.pdf").write_bytes(b"")
    (tmp_path / "Quotation Q-00003 Other.xlsx").write_bytes(b"")
    assert quotation.next_number(tmp_path) == 8


def test_policy_quotations():
    pdf = r"C:\Users\x\Documents\Acme Quotations\Quotation Q-00002 Seaview Hotel.pdf"
    send = {
        "to": "tan@seaview.example",
        "subject": "Quotation",
        "message": "Hi",
        "attachments": [pdf],
    }

    assert (
        decide("make_quotation", {"customer": "Seaview"}, PageContext()).verdict
        == ALLOW
    )
    assert decide("send_quotation", send, PageContext()).verdict == ASK
    assert (
        decide(
            "send_quotation", {**send, "to": "a@b.com, c@d.com"}, PageContext()
        ).verdict
        == DENY
    )
    assert (
        decide(
            "send_quotation",
            {**send, "attachments": [r"C:\x\setup.exe"]},
            PageContext(),
        ).verdict
        == DENY
    )
    assert (
        decide("send_quotation", {**send, "attachments": []}, PageContext()).verdict
        == DENY
    )


class FakeEmailer:
    """Records what is sent; Gmail is signed in."""

    def __init__(self):
        self.sent = []
        self.gmail = FakeGmail()

    async def send_quotation(self, **args):
        self.sent.append(args)
        return {"sent": True, "to": [args["to"]]}


async def test_every_quotation_email_is_asked_even_after_an_approval(tmp_path):
    emailer = FakeEmailer()
    gk = Gatekeeper(FakeBrowser(), emailer=emailer, audit_path=tmp_path / "audit.jsonl")
    pdf = tmp_path / "Quotation Q-00002 Seaview Hotel.pdf"
    send = {
        "to": "tan@seaview.example",
        "contact": "Ms Tan",
        "subject": "Quotation",
        "message": "Please find our quotation.",
        "attachments": [str(pdf)],
    }

    first = await gk.submit("call1", "send_quotation", send)
    await gk.resolve(first["approval_id"], approve=True, channel="web")
    second = await gk.submit("call1", "send_quotation", send)

    assert first["status"] == "needs_approval"
    assert len(emailer.sent) == 1
    assert second["status"] == "needs_approval"  # the call's approval does not cover it
    # The card shows who it goes to; it is the reply to the inquiry
    assert "tan@seaview.example" in second["summary"]
    assert emailer.sent[0]["to"] == "tan@seaview.example"
    assert emailer.sent[0]["subject"] == "Re: Quotation"


async def test_a_quotation_is_never_asked_while_gmail_is_signed_out(tmp_path):
    emailer = FakeEmailer()
    emailer.gmail.state = "signed_out"
    gk = Gatekeeper(FakeBrowser(), emailer=emailer, audit_path=tmp_path / "audit.jsonl")

    result = await gk.submit(
        "call1",
        "send_quotation",
        {"to": "a@b.example", "subject": "Q", "attachments": [str(tmp_path / "q.pdf")]},
    )

    assert result["status"] == "error" and "Open Gmail" in result["reason"]
    assert gk.pending() == []


async def test_the_quotation_goes_to_the_customer_with_no_copy(
    gmail, tmp_path, monkeypatch
):
    monkeypatch.delenv("QUOTE_SIGNATURE", raising=False)
    pdf = tmp_path / "Quotation Q-00002 Seaview Hotel.pdf"
    pdf.write_bytes(b"%PDF")

    result = await Emailer(gmail).send_quotation(
        to="tan@seaview.example",
        contact="Ms Tan",
        subject="Re: Quotation Q-00002",
        message="Thank you for your enquiry. Please find our quotation attached.",
        attachments=[str(pdf)],
    )

    [sent] = gmail.sent
    assert sent["to"] == ["tan@seaview.example"]
    assert sent["subject"] == "Re: Quotation Q-00002"
    assert sent["text"].startswith("Dear Ms Tan,\n\nThank you for your enquiry.")
    assert sent["text"].endswith("Best regards,\nSales Team")
    assert sent["attachments"] == [str(pdf.resolve())]
    assert result["to"] == ["tan@seaview.example"] and result["sent"]


async def test_a_quotation_goes_to_one_real_address(gmail, tmp_path):
    pdf = tmp_path / "q.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(EmailError, match="not an email address"):
        await Emailer(gmail).send_quotation(
            to="Ms Tan",
            contact="",
            subject="Re: Quotation",
            message="Hi",
            attachments=[str(pdf)],
        )
    assert gmail.sent == []


def test_saving_a_quotation_is_always_asked():
    assert (
        decide("save_quotation", {"quote_number": "Q-00002"}, PageContext()).verdict
        == ASK
    )


async def test_every_save_is_asked_even_after_an_approval(tmp_path):
    gk = Gatekeeper(FakeBrowser(), office=object(), audit_path=tmp_path / "audit.jsonl")
    gk._approved_sessions.add("call1")  # the user approved something earlier

    result = await gk.submit("call1", "save_quotation", {"quote_number": "Q-00002"})

    assert result["status"] == "needs_approval"
    assert "save Q-00002 as Excel and PDF" in result["summary"]


def test_the_draft_to_save_is_found_by_its_number(monkeypatch):
    def draft(n):
        return quotation.Draft(
            seaview(number=n), f"Book{n}", Path("x.xlsx"), Path("x.pdf")
        )

    monkeypatch.setattr(quotation, "_drafts", {})
    with pytest.raises(QuoteError, match="No quotation draft"):
        quotation._draft_key("Q-00002")
    monkeypatch.setattr(
        quotation, "_drafts", {"Q-00002": draft(2), "Q-00003": draft(3)}
    )
    assert quotation._draft_key("Q-00002") == "Q-00002"
    assert quotation._draft_key("2") == "Q-00002"
    assert quotation._draft_key("") == "Q-00003"  # the latest
    with pytest.raises(QuoteError, match="Q-00009"):
        quotation._draft_key("Q-00009")


def test_the_pdf_goes_to_the_desktop(monkeypatch, tmp_path):
    monkeypatch.delenv("QUOTE_PDF_DIR", raising=False)
    assert quotation.pdf_dir().name in ("Desktop", "桌面")
    monkeypatch.setenv("QUOTE_PDF_DIR", str(tmp_path))
    assert quotation.pdf_dir() == tmp_path


def test_the_reply_subject():
    from gatekeeper import reply_subject

    assert (
        reply_subject("Inquiry for Office Equipment")
        == "Re: Inquiry for Office Equipment"
    )
    assert reply_subject("RE: Inquiry") == "RE: Inquiry"
    assert reply_subject("") == "Re: Quotation"
