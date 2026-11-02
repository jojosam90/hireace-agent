import pytest

from policy import (
    ALLOW,
    ASK,
    DENY,
    PageContext,
    decide,
    looks_like_card_number,
)


def _ctx(url: str = "https://example.com", payment_fields: bool = False, field=None):
    return PageContext(url=url, payment_fields=payment_fields, field=field or {})


# --- Payments are always denied -------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://www.paypal.com/checkoutnow?token=abc",
        "https://checkout.stripe.com/c/pay/cs_test",
        "https://pay.google.com/gp/w/home",
        "https://shop.example.com/checkout",
        "https://store.example.com/cart/checkout/payment",
        "https://example.com/billing/update",
    ],
)
def test_navigating_to_payment_pages_is_denied(url: str) -> None:
    assert decide("open_url", {"url": url}, _ctx()).verdict == DENY


@pytest.mark.parametrize(
    "target",
    ["Buy now", "Place your order", "Proceed to checkout", "Pay $25.00", "Add payment method"],
)
def test_clicking_payment_controls_is_denied(target: str) -> None:
    assert decide("click", {"target": target}, _ctx()).verdict == DENY


def test_any_submit_on_a_page_with_card_fields_is_denied() -> None:
    ctx = _ctx(payment_fields=True)
    assert decide("click", {"target": "Continue"}, ctx).verdict == DENY
    assert decide("press_key", {"key": "Enter"}, ctx).verdict == DENY


@pytest.mark.parametrize(
    "field",
    [
        {"autocomplete": "cc-number"},
        {"name": "cardnumber"},
        {"id": "cvv"},
        {"label": "Expiry date (MM/YY)"},
    ],
)
def test_typing_into_card_fields_is_denied(field: dict) -> None:
    ctx = _ctx(field=field)
    assert decide("type_text", {"target": "x", "text": "hello"}, ctx).verdict == DENY


def test_typing_a_card_number_anywhere_is_denied() -> None:
    args = {"target": "Notes", "text": "4111 1111 1111 1111"}
    assert decide("type_text", args, _ctx()).verdict == DENY


def test_luhn_detection() -> None:
    assert looks_like_card_number("4111-1111-1111-1111")
    assert not looks_like_card_number("4111 1111 1111 1112")
    assert not looks_like_card_number("call me at 555 0100")


# --- Consequential actions ask the user ---------------------------------------


@pytest.mark.parametrize("target", ["Send", "Submit", "Delete account", "Post", "Add to cart"])
def test_consequential_clicks_require_approval(target: str) -> None:
    assert decide("click", {"target": target}, _ctx()).verdict == ASK


def test_typing_into_password_fields_requires_approval() -> None:
    ctx = _ctx(field={"type": "password"})
    assert decide("type_text", {"target": "Password", "text": "x"}, ctx).verdict == ASK


# --- Everyday browsing is allowed ---------------------------------------------


@pytest.mark.parametrize(
    ("action", "args"),
    [
        ("open_url", {"url": "https://www.youtube.com"}),
        ("read_page", {}),
        ("inspect_page", {}),
        ("click", {"target": "Search"}),
        ("type_text", {"target": "Search", "text": "cats"}),
        ("press_key", {"key": "Enter"}),
        ("scroll", {"direction": "down"}),
        ("open_browser", {}),
        ("close_browser", {}),
    ],
)
def test_everyday_browsing_is_allowed(action: str, args: dict) -> None:
    assert decide(action, args, _ctx()).verdict == ALLOW


def test_unknown_actions_are_denied() -> None:
    assert decide("run_shell", {"cmd": "rm -rf /"}, _ctx()).verdict == DENY


# --- Desktop (screen coordinate) control --------------------------------------


def _screen_ctx(target: str = "", in_browser: bool = True, **kw):
    """Screen input landing on the agent's own browser page (unless in_browser=False)."""
    return PageContext(target=target, in_browser=in_browser, **kw)


def test_screen_click_on_payment_button_is_denied() -> None:
    args = {"x": 500, "y": 400}
    assert decide("screen_click", args, _screen_ctx("Place order")).verdict == DENY


def test_screen_click_on_send_button_needs_approval() -> None:
    args = {"x": 500, "y": 400}
    assert decide("screen_click", args, _screen_ctx("Send")).verdict == ASK


def test_ordinary_screen_click_in_the_browser_is_allowed() -> None:
    assert decide("screen_click", {"x": 500, "y": 400}, _screen_ctx("Search")).verdict == ALLOW


@pytest.mark.parametrize(
    ("action", "args"),
    [
        ("screen_click", {"x": 10, "y": 10}),
        ("screen_drag", {"x": 1, "y": 1, "to_x": 50, "to_y": 50}),
        ("screen_type", {"text": "hello"}),
        ("screen_key", {"keys": "ctrl+s"}),
    ],
)
def test_screen_input_outside_the_browser_needs_approval(action: str, args: dict) -> None:
    # The user's own computer: desktop apps, files, other windows
    assert decide(action, args, _screen_ctx(in_browser=False)).verdict == ASK


def test_screen_click_anywhere_on_a_payment_page_is_denied() -> None:
    ctx = _screen_ctx("", payment_fields=True)
    assert decide("screen_click", {"x": 1, "y": 1}, ctx).verdict == DENY


def test_screen_typing_card_numbers_is_denied_even_outside_the_browser() -> None:
    args = {"text": "4111 1111 1111 1111"}
    assert decide("screen_type", args, _screen_ctx(in_browser=False)).verdict == DENY
    assert decide("screen_type", args, _screen_ctx()).verdict == DENY


def test_screen_typing_into_focused_card_field_is_denied() -> None:
    ctx = _screen_ctx(field={"autocomplete": "cc-number"})
    assert decide("screen_type", {"text": "hello"}, ctx).verdict == DENY


def test_screen_enter_on_payment_page_is_denied() -> None:
    ctx = _screen_ctx(payment_fields=True)
    assert decide("screen_key", {"keys": "enter"}, ctx).verdict == DENY
    assert decide("screen_key", {"keys": "ctrl+t"}, ctx).verdict == ALLOW


def test_new_tab_to_payment_page_is_denied() -> None:
    assert decide("new_tab", {"url": "https://www.paypal.com"}, _ctx()).verdict == DENY


def test_only_known_apps_can_be_opened() -> None:
    assert decide("open_app", {"app": "excel"}, _ctx()).verdict == ALLOW
    assert decide("open_app", {"app": "terminal"}, _ctx()).verdict == DENY
    assert decide("open_app", {"app": r"C:\Windows\System32\cmd.exe"}, _ctx()).verdict == DENY


@pytest.mark.parametrize(
    "path",
    [
        r"F:\Work\Acme proposal.docx",
        r"C:\Users\me\Downloads\budget.xlsx",
        r"C:\Users\me\Desktop\deck.pptx",
        r"C:\Users\me\Documents\contract.pdf",
        r"F:\Work\mockups",
    ],
)
def test_opening_documents_and_folders_is_allowed(path: str) -> None:
    assert decide("open_file", {"path": path}, _ctx()).verdict == ALLOW


@pytest.mark.parametrize(
    "path",
    [r"C:\Users\me\Downloads\setup.exe", r"F:\tools\run.BAT", r"C:\x\script.ps1", r"C:\x\a.lnk"],
)
def test_opening_programs_or_scripts_is_denied(path: str) -> None:
    assert decide("open_file", {"path": path}, _ctx()).verdict == DENY


def test_opening_macro_documents_needs_approval() -> None:
    assert decide("open_file", {"path": r"F:\Work\report.xlsm"}, _ctx()).verdict == ASK


def test_searching_files_is_allowed() -> None:
    assert decide("find_files", {"query": "proposal"}, _ctx()).verdict == ALLOW


def test_closing_a_window_needs_approval() -> None:
    assert decide("close_window", {"title": "Book1 - Excel"}, _ctx()).verdict == ASK


@pytest.mark.parametrize(
    ("action", "args"),
    [
        ("screenshot", {}),
        ("screen_move", {"x": 5, "y": 5}),
        ("screen_scroll", {"direction": "down"}),
        ("list_windows", {}),
        ("focus_window", {"title": "Excel"}),
        ("list_tabs", {}),
        ("switch_tab", {"index": 1}),
        ("close_tab", {}),
        ("new_tab", {"url": "https://example.com"}),
    ],
)
def test_everyday_desktop_control_is_allowed(action: str, args: dict) -> None:
    assert decide(action, args, _ctx()).verdict == ALLOW


@pytest.mark.parametrize(
    "target", ["Accept", "Accept all", "Accept All Cookies", "I agree", "Got it", "Allow all"]
)
def test_cookie_consent_buttons_do_not_need_approval(target: str) -> None:
    assert decide("click", {"target": target}, _ctx()).verdict == ALLOW


@pytest.mark.parametrize("target", ["Accept invitation", "Agree and continue", "Accept and send"])
def test_consent_words_with_real_actions_still_ask(target: str) -> None:
    assert decide("click", {"target": target}, _ctx()).verdict == ASK


def test_agree_and_pay_is_still_a_payment() -> None:
    assert decide("click", {"target": "Agree and pay"}, _ctx()).verdict == DENY


# --- Office documents ----------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "args"),
    [
        ("office_read", {"app": "powerpoint"}),
        ("office_go_to", {"app": "excel", "target": "B5"}),
        ("word_edit", {"find": "100 dollars", "replace_with": "120 dollars"}),
        ("excel_set_cells", {"cells": {"B3": "120"}}),
        ("ppt_edit", {"slide": 2, "shape": "Title 1", "text": "Pricing"}),
    ],
)
def test_reading_and_editing_open_documents_is_allowed(action: str, args: dict) -> None:
    assert decide(action, args, _ctx()).verdict == ALLOW


def test_saving_a_document_asks() -> None:
    assert decide("office_save", {"app": "word"}, _ctx()).verdict == ASK


@pytest.mark.parametrize(
    ("action", "args"),
    [
        ("word_edit", {"paragraph": 2, "text": "Card 4111 1111 1111 1111"}),
        ("excel_set_cells", {"cells": {"B3": "4111-1111-1111-1111"}}),
    ],
)
def test_card_numbers_are_never_written_into_documents(action: str, args: dict) -> None:
    assert decide(action, args, _ctx()).verdict == DENY
