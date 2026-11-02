"""Deterministic safety policy for agent actions.

Every action the agent proposes is classified as ALLOW, ASK (needs the user's
approval) or DENY. Payment-related actions are always DENY and can never be
approved. This module has no I/O so it can be tested and audited in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PureWindowsPath
from urllib.parse import urlparse

ALLOW = "allow"
ASK = "ask"
DENY = "deny"

PAYMENT_DENIAL = (
    "Payments are never allowed. Tell the user to complete any payment themselves."
)

# Payment processors and wallets. Subdomains are matched too.
PAYMENT_DOMAINS = (
    "paypal.com",
    "paypal.me",
    "stripe.com",
    "pay.google.com",
    "payments.google.com",
    "pay.amazon.com",
    "pay.shopify.com",
    "shop.app",
    "klarna.com",
    "afterpay.com",
    "affirm.com",
    "venmo.com",
    "cash.app",
    "razorpay.com",
    "paytm.com",
    "alipay.com",
    "adyen.com",
    "braintreegateway.com",
    "checkout.com",
    "2checkout.com",
    "payoneer.com",
    "wise.com",
    "skrill.com",
    "coinbase.com",
)

_PAYMENT_PATH = re.compile(
    r"/(checkout|payments?|pay|billing|purchase|place-?order|order/confirm)(/|$|\?|-|_)",
    re.IGNORECASE,
)

_PAYMENT_CONTROL = re.compile(
    r"\b(buy|pay|purchase|checkout|check out|place (your )?order|order now|"
    r"complete (your )?order|submit order|donate|add (a )?(payment|card)|"
    r"payment method|proceed to payment|confirm payment|subscribe and pay)\b",
    re.IGNORECASE,
)

_CARD_FIELD = re.compile(
    r"\b(cc-|card ?number|cardnumber|cvv|cvc|csc|security code|expir|exp-?date|iban)",
    re.IGNORECASE,
)

_CONSEQUENTIAL_CONTROL = re.compile(
    r"\b(send|submit|delete|remove|confirm|post|publish|sign up|register|"
    r"book|reserve|add to (cart|basket|bag)|subscribe|unsubscribe|transfer|"
    r"accept|agree|share|invite|reply|archive)\b",
    re.IGNORECASE,
)

_SUBMIT_KEYS = {"Enter"}

READ_ONLY_ACTIONS = {
    "read_page",
    "inspect_page",
    "go_back",
    "take_screenshot",
    "scroll",
    "open_browser",
    "close_browser",
    # Tabs of the agent's own browser, and desktop actions that change nothing
    "list_tabs",
    "switch_tab",
    "close_tab",
    "screenshot",
    "screen_move",
    "screen_scroll",
    "list_windows",
    "focus_window",
    "find_browser_tab",
    # Opens an email or list row (rows only: never a button or link)
    "open_browser_item",
    "read_browser_window",
    "find_files",
    # Office documents: reading and moving around change nothing
    "office_read",
    "office_go_to",
}
# Keep in sync with APPS in local_desktop.py
DESKTOP_APPS = {
    "word",
    "excel",
    "powerpoint",
    "outlook",
    "notepad",
    "files",
    "calculator",
}
# Real mouse/keyboard input: needs approval unless it lands in the agent's browser
SCREEN_INPUT_ACTIONS = {"screen_click", "screen_drag", "screen_type", "screen_key"}
KNOWN_ACTIONS = (
    READ_ONLY_ACTIONS
    | SCREEN_INPUT_ACTIONS
    | {
        "open_url",
        "new_tab",
        "click",
        "type_text",
        "press_key",
        "open_app",
        "close_window",
        "open_file",
        "word_edit",
        "excel_set_cells",
        "ppt_edit",
        "office_save",
        "send_email",
        "make_quotation",
        "save_quotation",
        "send_quotation",
    }
)
OFFICE_EDIT_ACTIONS = {"word_edit", "excel_set_cells", "ppt_edit"}
_EMAIL = re.compile(r"[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}")

# Opening these runs a program or script, not a document
_EXECUTABLE_EXTENSIONS = {
    ".exe",
    ".msi",
    ".msix",
    ".appx",
    ".bat",
    ".cmd",
    ".com",
    ".ps1",
    ".psm1",
    ".vbs",
    ".vbe",
    ".js",
    ".jse",
    ".wsf",
    ".wsh",
    ".hta",
    ".scr",
    ".pif",
    ".cpl",
    ".msc",
    ".lnk",
    ".url",
    ".reg",
    ".jar",
    ".py",
    ".pyw",
    ".dll",
    ".sys",
    ".inf",
    ".application",
    ".gadget",
    ".sh",
}
# Office documents that can carry macros
_MACRO_EXTENSIONS = {
    ".xlsm",
    ".xlsb",
    ".xltm",
    ".docm",
    ".dotm",
    ".pptm",
    ".potm",
    ".ppsm",
}


@dataclass(frozen=True)
class PageContext:
    """What the executor knows about the page an action would affect."""

    url: str = ""
    payment_fields: bool = False
    # Attributes of the field being typed into: autocomplete, name, id, type, label
    field: dict = field(default_factory=dict)
    # For screen-coordinate clicks: text/label of the browser element under the
    # pointer ("" when the point is not on a web page)
    target: str = ""
    # Screen input lands in the agent's own browser page (focused, and the point
    # is inside it) rather than somewhere else on the user's computer
    in_browser: bool = False


@dataclass(frozen=True)
class Decision:
    verdict: str
    reason: str


def is_payment_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if any(host == d or host.endswith("." + d) for d in PAYMENT_DOMAINS):
        return True
    return bool(_PAYMENT_PATH.search(parsed.path or ""))


def looks_like_card_number(text: str) -> bool:
    """True if text contains a 13-19 digit sequence that passes the Luhn check."""
    for match in re.finditer(r"(?:\d[ -]?){13,19}", text):
        digits = [int(c) for c in match.group() if c.isdigit()]
        if not 13 <= len(digits) <= 19:
            continue
        total = 0
        for i, d in enumerate(reversed(digits)):
            if i % 2:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        if total % 10 == 0:
            return True
    return False


def _is_card_field(attrs: dict) -> bool:
    return any(_CARD_FIELD.search(str(v)) for v in attrs.values() if v)


# Cookie / privacy consent banners: harmless, and asking every time would
# interrupt almost every site visit. Exact labels only ("Accept and send" still asks).
_CONSENT_ONLY = re.compile(
    r"^\s*(accept|accept all|accept all cookies|accept cookies|allow all|allow cookies|"
    r"i agree|agree|got it|ok|okay)\s*[.!]?\s*$",
    re.IGNORECASE,
)


def _click_decision(target: str, on_payment_page: bool) -> Decision:
    if _PAYMENT_CONTROL.search(target) or on_payment_page:
        return Decision(DENY, PAYMENT_DENIAL)
    if _CONSENT_ONLY.match(target):
        return Decision(ALLOW, "Cookie/privacy consent.")
    if _CONSEQUENTIAL_CONTROL.search(target):
        return Decision(ASK, f"Clicking {target!r} may have real consequences.")
    return Decision(ALLOW, "Click.")


def _type_decision(text: str, field_attrs: dict) -> Decision:
    if _is_card_field(field_attrs) or looks_like_card_number(text):
        return Decision(DENY, PAYMENT_DENIAL)
    if str(field_attrs.get("type", "")).lower() == "password":
        return Decision(ASK, "Typing into a password field.")
    return Decision(ALLOW, "Typing.")


def decide(action: str, args: dict, ctx: PageContext) -> Decision:
    if action not in KNOWN_ACTIONS:
        return Decision(DENY, f"Unknown action {action!r}.")

    if action == "open_app":
        if args.get("app") not in DESKTOP_APPS:
            return Decision(
                DENY, f"Only these apps can be opened: {sorted(DESKTOP_APPS)}."
            )
        return Decision(ALLOW, "Open app.")

    if action == "close_window":
        return Decision(
            ASK, "Closing a window on the user's computer can lose unsaved work."
        )

    if action == "open_file":
        extension = PureWindowsPath(str(args.get("path", ""))).suffix.lower()
        if extension in _EXECUTABLE_EXTENSIONS:
            return Decision(
                DENY,
                "Only documents and folders can be opened, never programs or scripts.",
            )
        if extension in _MACRO_EXTENSIONS:
            return Decision(ASK, "A macro-enabled document: its macros could run.")
        return Decision(ALLOW, "Open document.")

    if action in OFFICE_EDIT_ACTIONS:
        # Unsaved edits, highlighted for the user and undoable: allowed, except card numbers
        written = " ".join(
            str(v) for v in [*args.values(), *dict(args.get("cells") or {}).values()]
        )
        if looks_like_card_number(written):
            return Decision(DENY, PAYMENT_DENIAL)
        return Decision(ALLOW, "Edit an open document (highlighted, not saved).")

    if action == "send_email":
        to = args.get("to") or []
        to = to if isinstance(to, list) else [to]
        if not to or not all(_EMAIL.fullmatch(str(a).strip()) for a in to):
            return Decision(
                DENY,
                "Name who it goes to: the email addresses the user gave, or the "
                "sender of the email being answered. Ask the user if unsure.",
            )
        files = [str(a) for a in args.get("attachments") or []]
        if any(
            PureWindowsPath(f).suffix.lower() in _EXECUTABLE_EXTENSIONS for f in files
        ):
            return Decision(
                DENY, "Only documents can be attached, never programs or scripts."
            )
        changes = " ".join(str(c) for c in args.get("changes") or [])
        if looks_like_card_number(
            f"{args.get('subject', '')} {args.get('message', '')} {changes}"
        ):
            return Decision(DENY, PAYMENT_DENIAL)
        return Decision(ASK, f"Sending an email to {', '.join(map(str, to))}.")

    if action == "office_save":
        return Decision(ASK, "Saving overwrites the file on the user's computer.")

    if action == "make_quotation":
        # A new Excel file and PDF from the template: nothing existing is changed
        if looks_like_card_number(" ".join(str(v) for v in args.values())):
            return Decision(DENY, PAYMENT_DENIAL)
        return Decision(ALLOW, "A quotation draft (nothing is saved).")

    if action == "save_quotation":
        return Decision(ASK, "Saves the approved quotation as Excel and PDF.")

    if action == "send_quotation":
        to = str(args.get("to", "")).strip()
        if not _EMAIL.fullmatch(to):
            return Decision(
                DENY, "A quotation goes to one email address, the customer's."
            )
        files = [PureWindowsPath(str(a)) for a in args.get("attachments") or []]
        if not files or any(f.suffix.lower() not in {".pdf", ".xlsx"} for f in files):
            return Decision(
                DENY, "Only the quotation's PDF or Excel file can be attached."
            )
        if looks_like_card_number(
            f"{args.get('subject', '')} {args.get('message', '')}"
        ):
            return Decision(DENY, PAYMENT_DENIAL)
        return Decision(ASK, f"Emails a quotation to a customer ({to}).")

    if action in ("open_url", "new_tab"):
        if is_payment_url(str(args.get("url", ""))):
            return Decision(DENY, PAYMENT_DENIAL)
        return Decision(ALLOW, "Navigation.")

    if action in READ_ONLY_ACTIONS:
        return Decision(ALLOW, "Read-only.")

    if action == "screen_type" and looks_like_card_number(str(args.get("text", ""))):
        return Decision(DENY, PAYMENT_DENIAL)  # wherever it would be typed

    if action in SCREEN_INPUT_ACTIONS and not ctx.in_browser:
        return Decision(
            ASK, "Mouse or keyboard input on the user's computer, outside the browser."
        )

    on_payment_page = ctx.payment_fields or is_payment_url(ctx.url)

    if action == "click":
        return _click_decision(str(args.get("target", "")), on_payment_page)

    if action in ("screen_click", "screen_drag"):
        # ctx.target is what the browser reports under the pointer
        return _click_decision(ctx.target, on_payment_page)

    if action in ("type_text", "screen_type"):
        return _type_decision(str(args.get("text", "")), ctx.field)

    if action in ("press_key", "screen_key"):
        keys = str(args.get("key") or args.get("keys") or "")
        submits = any(k.strip().capitalize() in _SUBMIT_KEYS for k in keys.split("+"))
        if submits and on_payment_page:
            return Decision(DENY, PAYMENT_DENIAL)
        return Decision(ALLOW, "Key press.")

    return Decision(DENY, "Unhandled action.")
