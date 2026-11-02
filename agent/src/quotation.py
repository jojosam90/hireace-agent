"""Quotations: the company's Excel template filled in as a new file, plus its PDF.

The agent picks the products (price_list.json) and quantities (no shipping charge
or tax unless the user asks); this works out the numbers and fills the template
(QUOTE_TEMPLATE, else agent/templates/quotation.xlsx) in the user's Excel, on screen
one cell at a time, so they watch the draft being written; the logo and formatting
stay exactly as designed. The draft stays open unsaved until the user approves it;
then, again on screen, it is saved as a new file with the next number, saved as PDF,
the PDF opens for preview and the draft closes. The Excel file goes to
Documents/HireAce Quotations (or QUOTE_DIR), the PDF to the Desktop (or QUOTE_PDF_DIR);
the template itself is never changed.

The template is found by its labels, not fixed cells: "Date:", "Quote #:",
"Customer ID:", "Purchase order #:" (values one column to the right), "Billed to",
the "Description" header of the item rows, and SUBTOTAL, DISCOUNT, (TAX RATE), TAX
and TOTAL. Item rows are added or removed to fit.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("hireace.quotation")

AGENT_DIR = Path(__file__).resolve().parent.parent
VALID_DAYS = 30
WIDE_COLON = chr(0xFF1A)  # the full-width colon of the company's sample
MAX_BILLED_TO_LINES = 5


class QuoteError(Exception):
    """A user-facing quotation problem."""


def price_list_path() -> Path:
    return Path(os.environ.get("QUOTE_PRICE_LIST") or AGENT_DIR / "price_list.json")


def template_path() -> Path:
    """QUOTE_TEMPLATE (the user's own template file) if it exists, else the bundled copy."""
    chosen = os.environ.get("QUOTE_TEMPLATE", "").strip()
    if chosen and Path(chosen).is_file():
        return Path(chosen)
    return AGENT_DIR / "templates" / "quotation.xlsx"


def output_dir() -> Path:
    if folder := os.environ.get("QUOTE_DIR"):
        return Path(folder)
    return Path.home() / "Documents" / "HireAce Quotations"


def pdf_dir() -> Path:
    """Where the approved quotation's PDF goes: the user's Desktop (QUOTE_PDF_DIR
    changes it). Windows' own Desktop folder, so a Desktop moved to OneDrive counts."""
    if folder := os.environ.get("QUOTE_PDF_DIR"):
        return Path(folder)
    with contextlib.suppress(Exception):
        from win32com.shell import shell, shellcon

        return Path(shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOPDIRECTORY, None, 0))
    return Path.home() / "Desktop"


def load_price_list(path: Path | None = None) -> list[dict]:
    data = json.loads((path or price_list_path()).read_text(encoding="utf-8"))
    return data["products"]


@dataclass
class Line:
    text: str  # the Description cell: item, description, brand, model
    unit_price: float
    quantity: int

    @property
    def amount(self) -> float:
        return round(self.unit_price * self.quantity, 2)


@dataclass
class Quote:
    number: int
    date: datetime.date
    customer: str
    contact: str = ""
    customer_email: str = ""
    address: list[str] = field(default_factory=list)
    phone: str = ""
    lines: list[Line] = field(default_factory=list)
    shipping: float = 0.0
    tax_rate: float = 0.0  # percent
    discount: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def quote_no(self) -> str:
        return f"{self.number:05d}"

    @property
    def customer_id(self) -> str:
        """Initials of the customer's name and the quote number, e.g. SH00002."""
        words = re.findall(r"[A-Za-z]+", self.customer.split(",")[0])
        initials = "".join(
            w[0] for w in words if w.lower() not in {"a", "an", "the", "of"}
        )
        return f"{initials[:3].upper() or 'CUS'}{self.quote_no}"

    @property
    def valid_until(self) -> datetime.date:
        return self.date + datetime.timedelta(days=VALID_DAYS)

    @property
    def subtotal(self) -> float:
        return round(sum(line.amount for line in self.lines), 2)

    @property
    def tax(self) -> float:
        # Tax on the goods and the delivery (as GST is charged), after the discount
        return round(
            (self.subtotal - self.discount + self.shipping) * self.tax_rate / 100, 2
        )

    @property
    def total(self) -> float:
        return round(self.subtotal - self.discount + self.shipping + self.tax, 2)

    @property
    def file_stem(self) -> str:
        name = re.sub(r'[<>:"/\\|?*]+', "", self.customer.split(",")[0]).strip()
        return f"Quotation Q-{self.quote_no} {name}".strip()

    def billed_to(self) -> list[str]:
        """As in the company's sample: company, address lines, phone."""
        address = [a.strip() for a in self.address if a.strip()]
        if not address and self.contact:
            address = [f"Attn: {self.contact}"]  # something to address it to
        phone = [self.phone.strip()] if self.phone.strip() else []
        # The template has room for five lines: join the last address lines if needed
        room = MAX_BILLED_TO_LINES - 1 - len(phone)
        if len(address) > room:
            address = [*address[: room - 1], ", ".join(address[room - 1 :])]
        return [self.customer, *address, *phone]

    def full_notes(self) -> str:
        """Only the notes asked for: the sample leaves the box empty."""
        return "\n".join(n.strip() for n in self.notes if n.strip())


def _date(date: datetime.date) -> str:
    return f"{date:%m/%d/%Y}"  # the template's MM/DD/YYYY


def _line_text(product: dict) -> str:
    # Written as in the company's sample (full-width colons after Item and Description)
    return (
        f"Item{WIDE_COLON} {product['item']}\nDescription{WIDE_COLON}{product['description']}\n"
        f"Brand: {product['brand']}\nModel: {product['model']}"
    )


def build_quote(
    *,
    customer: str,
    items: list[dict],
    number: int,
    date: datetime.date,
    price_list: list[dict],
    contact: str = "",
    customer_email: str = "",
    address: list[str] | None = None,
    phone: str = "",
    shipping: float = 0.0,
    tax_rate: float = 0.0,
    discount: float = 0.0,
    notes: list[str] | None = None,
) -> Quote:
    """The quotation from the agent's choices; checks every item against the price list.

    Each item: {"model": ..., "quantity": ...} and optionally "unit_price" (a price the
    user gave instead of the list price). A product not in the price list needs
    "description" and "unit_price".
    """
    if not customer.strip():
        raise QuoteError("The customer's name is needed.")
    if not items:
        raise QuoteError("A quotation needs at least one item.")
    for name, value in (
        ("shipping", shipping),
        ("tax rate", tax_rate),
        ("discount", discount),
    ):
        if value < 0:
            raise QuoteError(f"The {name} cannot be negative.")
    by_model = {p["model"].casefold(): p for p in price_list}
    lines = []
    for item in items:
        quantity = int(item.get("quantity") or 0)
        if quantity <= 0:
            raise QuoteError(
                f"Give a quantity for {item.get('model') or item.get('description')!r}."
            )
        product = by_model.get(str(item.get("model", "")).strip().casefold())
        price = item.get("unit_price")
        if product is not None:
            unit_price = (
                float(price)
                if price not in (None, "")
                else float(product["unit_price"])
            )
            lines.append(Line(_line_text(product), unit_price, quantity))
        elif item.get("description") and price not in (None, ""):
            lines.append(Line(str(item["description"]), float(price), quantity))
        else:
            models = ", ".join(f"{p['model']} ({p['item']})" for p in price_list)
            raise QuoteError(
                f"{item.get('model')!r} is not in the price list ({models}). For another "
                "product give its description and unit_price."
            )
    return Quote(
        number=number,
        date=date,
        customer=customer.strip(),
        contact=contact.strip(),
        customer_email=customer_email.strip(),
        address=list(address or []),
        phone=str(phone or ""),
        lines=lines,
        shipping=float(shipping),
        tax_rate=float(tax_rate),
        discount=float(discount),
        notes=list(notes or []),
    )


def next_number(folder: Path) -> int:
    """One more than the highest quotation number already in the folder."""
    numbers = [
        int(m.group(1))
        for f in folder.glob("Quotation Q-*")
        if (m := re.match(r"Quotation Q-(\d+)", f.name))
    ]
    return max(numbers, default=0) + 1


def summary(quote: Quote, xlsx: Path, pdf: Path) -> dict:
    return {
        "quote_number": f"Q-{quote.quote_no}",
        "customer": quote.customer,
        "items": [
            {
                "text": line.text.splitlines()[0],
                "quantity": line.quantity,
                "amount": line.amount,
            }
            for line in quote.lines
        ],
        "subtotal": quote.subtotal,
        "discount": quote.discount,
        "shipping": quote.shipping,
        "tax_rate": quote.tax_rate,
        "tax": quote.tax,
        "total": quote.total,
        "currency": "SGD",
        "excel": str(xlsx),
        "pdf": str(pdf),
    }


# --- Filling the template (Excel, on the Office worker thread) -------------------------

PACE = 0.3  # seconds per filled cell when filling on screen, so the user can follow
XL_MAXIMIZED = -4137
XL_WORKBOOK = 51  # .xlsx


@dataclass
class Draft:
    """A filled-in quotation open in the user's Excel, not saved yet."""

    quote: Quote
    book: str  # the workbook's name in Excel, e.g. "Quotation Template.xlsx"
    xlsx: Path  # where it is saved once the user approves
    pdf: Path


# Open drafts by quote number ("Q-00002"); only the Office worker thread uses this
_drafts: dict[str, Draft] = {}


def make(args: dict, *, live: bool = True) -> dict:
    """Prepare a quotation from the template.

    live (the agent): a draft filled in on screen in the user's Excel, one cell at a
    time, and left open unsaved; save() saves it once the user approves. Otherwise
    (tests, scripts): filled in a hidden Excel and saved with its PDF at once.
    """
    # Rebuilding closes the open draft and loses anything changed in it by hand
    replace_draft = args.pop("replace_draft", False)
    if live and _open_drafts() and not replace_draft:
        raise QuoteError(
            "A quotation draft is already open and nothing has been changed. To change "
            "a value in it use excel_replace, in that same cell. Only to add or remove "
            "products: ask the user, as starting again loses changes made in the draft, "
            "then call this with replace_draft."
        )
    folder = output_dir()
    folder.mkdir(parents=True, exist_ok=True)
    template = template_path()
    if not template.is_file():
        raise QuoteError(
            f"The quotation template is missing: {template}. Put the company's "
            "Excel template there, or choose one in Settings (the gear icon)."
        )
    quote = build_quote(
        number=next_number(folder),
        date=datetime.date.today(),
        price_list=load_price_list(),
        **args,
    )
    xlsx = folder / f"{quote.file_stem}.xlsx"
    pdf = pdf_dir() / f"{quote.file_stem}.pdf"  # the PDF on the Desktop
    if not live:
        fill_with_excel(quote, template, xlsx, pdf)
        return summary(quote, xlsx, pdf)
    book = _draft_in_excel(quote, template)
    _drafts[f"Q-{quote.quote_no}"] = Draft(quote, book, xlsx, pdf)
    result = summary(quote, xlsx, pdf)
    del result["excel"], result["pdf"]  # nothing is saved until the user approves
    return {**result, "status": "draft open in Excel, not saved yet"}


def save(quote_number: str = "") -> dict:
    """The approved draft, on screen: save it as Excel, save the PDF, open the PDF
    to preview it, then close the draft in Excel (and Excel, if nothing else is open).
    """
    import win32com.client

    key = _draft_key(quote_number)
    draft = _drafts[key]
    excel = _Patient(_retry(lambda: win32com.client.Dispatch("Excel.Application")))
    try:
        book = excel.Workbooks(draft.book)
    except Exception as exc:
        _drafts.pop(key, None)
        raise QuoteError(
            f"The draft of {key} is no longer open in Excel; prepare it again."
        ) from exc
    draft.xlsx.parent.mkdir(parents=True, exist_ok=True)
    draft.pdf.parent.mkdir(parents=True, exist_ok=True)
    sheet = book.Worksheets(1)
    _show_window(excel, book, sheet)

    excel.StatusBar = f"HireAce: saving {draft.xlsx.name}"
    time.sleep(1.0)
    alerts = excel.DisplayAlerts
    excel.DisplayAlerts = False
    try:
        book.SaveAs(str(draft.xlsx), XL_WORKBOOK)  # the window title changes to it
    finally:
        excel.DisplayAlerts = alerts
    time.sleep(1.5)

    excel.StatusBar = f"HireAce: saving {draft.pdf.name}"
    book.ExportAsFixedFormat(0, str(draft.pdf))  # 0: PDF
    excel.StatusBar = False  # Excel's own status text again
    time.sleep(1.0)

    os.startfile(draft.pdf)  # our own PDF, to preview
    time.sleep(2.5)  # the PDF opens in front before the draft closes
    book.Close(False)  # already saved
    with contextlib.suppress(Exception):
        if excel.Workbooks.Count == 0:
            excel.Quit()
    del _drafts[key]
    return {**summary(draft.quote, draft.xlsx, draft.pdf), "status": "saved"}


def _open_drafts() -> list[str]:
    """Drafts still open in Excel: the user may have closed one themselves."""
    import win32com.client

    try:
        excel = win32com.client.GetActiveObject("Excel.Application")
        open_books = {
            excel.Workbooks(i).Name for i in range(1, excel.Workbooks.Count + 1)
        }
    except Exception:
        open_books = set()
    for key in [k for k, draft in _drafts.items() if draft.book not in open_books]:
        del _drafts[key]
    return list(_drafts)


def _draft_key(quote_number: str) -> str:
    if not _drafts:
        raise QuoteError("No quotation draft is open; prepare one first.")
    digits = re.sub(r"\D", "", quote_number)
    if not digits:
        return next(reversed(_drafts))  # the latest draft
    key = f"Q-{int(digits):05d}"
    if key not in _drafts:
        raise QuoteError(f"No open draft {key}; open drafts: {', '.join(_drafts)}.")
    return key


def _draft_in_excel(quote: Quote, template: Path) -> str:
    """The template opened (read-only) in the user's Excel, filled in on screen.

    Earlier unsaved drafts (replaced by this one) are closed. Returns its name.
    """
    import pywintypes
    import win32com.client

    try:
        excel = _Patient(_retry(lambda: win32com.client.Dispatch("Excel.Application")))
        excel.Visible = True
        for old in list(_drafts.values()):
            with contextlib.suppress(Exception):
                excel.Workbooks(old.book).Close(False)
        _drafts.clear()
        # The template file itself, read-only: the user sees "Quotation
        # Template.xlsx" being filled in, yet the file on disk is never changed (the
        # approved quotation is saved under its own name)
        book = excel.Workbooks.Open(str(template), ReadOnly=True)
        sheet = book.Worksheets(1)
        _show_window(excel, book, sheet)
        excel.Interactive = False  # a stray click or key cannot interrupt it
        try:
            _fill(excel, sheet, quote, live=True)
        except Exception:
            with contextlib.suppress(Exception):
                book.Close(False)
            raise
        finally:
            with contextlib.suppress(Exception):
                excel.Interactive = True
        return book.Name
    except pywintypes.com_error as exc:
        if exc.hresult in _BUSY:
            raise QuoteError(
                "Excel is busy: a cell is being edited or a dialog is open. Press Enter "
                "or Esc in Excel, then try again."
            ) from exc
        raise


# "Call was rejected by callee" / "retry later": Excel is busy (starting, opening a
# file, or the user is typing in a cell); the call works if made again shortly
_BUSY = {-2147418111, -2147417846}
_BUSY_WAIT = 30.0


def _retry(call):
    import pywintypes

    deadline = time.monotonic() + _BUSY_WAIT
    while True:
        try:
            return call()
        except pywintypes.com_error as exc:
            if exc.hresult not in _BUSY or time.monotonic() > deadline:
                raise
            time.sleep(0.2)


class _Patient:
    """A COM object whose every property and call is retried while Excel is busy."""

    def __init__(self, obj) -> None:
        object.__setattr__(self, "_obj", obj)

    def __getattr__(self, name: str):
        return _patient(_retry(lambda: getattr(self._obj, name)))

    def __setattr__(self, name: str, value) -> None:
        _retry(lambda: setattr(self._obj, name, _raw(value)))

    def __call__(self, *args, **kwargs):
        args = [_raw(a) for a in args]
        kwargs = {k: _raw(v) for k, v in kwargs.items()}
        return _patient(_retry(lambda: self._obj(*args, **kwargs)))


def _patient(value):
    return _Patient(value) if callable(value) or hasattr(value, "_oleobj_") else value


def _raw(value):
    return value._obj if isinstance(value, _Patient) else value


def fill_with_excel(quote: Quote, template: Path, xlsx: Path, pdf: Path) -> None:
    """In a hidden Excel of its own: copy the template to xlsx, fill the copy, save
    it and its PDF. The template is never changed."""
    import win32com.client

    shutil.copyfile(template, xlsx)
    excel = _Patient(win32com.client.DispatchEx("Excel.Application"))
    excel.Visible = False
    try:
        book = excel.Workbooks.Open(str(xlsx))
        try:
            _fill(excel, book.Worksheets(1), quote)
            book.Save()
            book.ExportAsFixedFormat(0, str(pdf))  # 0: PDF
        finally:
            book.Close(False)
    except Exception:
        with contextlib.suppress(OSError):
            xlsx.unlink()  # no half-filled quotation left behind
        raise
    finally:
        with contextlib.suppress(Exception):
            excel.Quit()


def _show_window(excel, book, sheet) -> None:
    """Bring the workbook to the front, maximised, at the top of the sheet."""
    from local_desktop import focus_window_handle

    with contextlib.suppress(Exception):
        book.Activate()
        sheet.Activate()
        excel.WindowState = XL_MAXIMIZED
        excel.Goto(sheet.Range("A1"), True)
    try:
        in_front = focus_window_handle(int(excel.Hwnd))
    except Exception:
        in_front = False
    logger.info(
        "quotation Excel window %s", "in front" if in_front else "raised on top"
    )


class _Writer:
    """Writes cells; on screen it moves to each cell first and pauses after it."""

    def __init__(self, excel, live: bool) -> None:
        self.excel = excel
        self.live = live

    def _show(self, cell) -> None:
        if self.live:
            with contextlib.suppress(Exception):  # only a visual aid
                self.excel.Goto(cell)

    def _pause(self) -> None:
        if self.live:
            time.sleep(PACE)

    def text(self, cell, value: str) -> None:
        self._show(cell)
        cell.NumberFormat = "@"  # as written: keeps 00002, no date conversion
        cell.Value2 = value
        self._pause()

    def value(self, cell, value) -> None:
        self._show(cell)
        cell.Value2 = value
        self._pause()

    def formula(self, cell, formula: str) -> None:
        self._show(cell)
        cell.Formula = formula
        self._pause()


def _labels(sheet) -> dict[str, tuple[int, int]]:
    """Each label's (row, column), from one read of the sheet."""
    used = sheet.UsedRange
    top, left = used.Row, used.Column
    values = used.Value2 or ()
    found: dict[str, tuple[int, int]] = {}
    for r, row in enumerate(values):
        for c, value in enumerate(row):
            if isinstance(value, str) and value.strip():
                found.setdefault(value.strip().casefold(), (top + r, left + c))
    return found


def _find(labels: dict, *names: str) -> tuple[int, int]:
    for name in names:
        if name.casefold() in labels:
            return labels[name.casefold()]
    raise QuoteError(f"The template has no {names[0]!r} label.")


def _fill(excel, sheet, quote: Quote, *, live: bool = False) -> None:
    write = _Writer(excel, live)
    labels = _labels(sheet)

    # Header: the date, quote number and customer ID; the rest stays as designed
    for label, value in (
        ("Date:", _date(quote.date)),
        ("Quote #:", quote.quote_no),
        ("Customer ID:", quote.customer_id),
    ):
        row, col = _find(labels, label)
        write.text(sheet.Cells(row, col + 1), value)

    row, col = _find(labels, "Billed to")
    first = row + 2
    sheet.Range(
        sheet.Cells(first, col), sheet.Cells(first + MAX_BILLED_TO_LINES - 1, col)
    ).ClearContents()
    for i, text in enumerate(quote.billed_to()):
        cell = sheet.Cells(first + i, col)
        # Plain values as in the sample; text format only where Excel could turn
        # the line into a number or date ("97431319", "11-12")
        if re.fullmatch(r"[\d+\-/.]+", text.strip()):
            write.text(cell, text)
        else:
            write.value(cell, text)

    # Money cells use the template's own format (that of the SUBTOTAL amount)
    subtotal_row, _ = _find(labels, "SUBTOTAL")
    money = sheet.Cells(subtotal_row, 5).NumberFormat

    # Item rows: between the Description header (and its spacer row) and the totals
    header, _ = _find(labels, "Description")
    first_item = header + 2
    existing = subtotal_row - 2 - first_item + 1
    wanted = len(quote.lines)
    if wanted > existing:
        last = first_item + existing - 1
        sheet.Rows(f"{last}:{last + wanted - existing - 1}").Insert(
            -4121, 0
        )  # down, format from above
    elif wanted < existing:
        sheet.Rows(f"{first_item + wanted}:{first_item + existing - 1}").Delete()
    for i, line in enumerate(quote.lines):
        r = first_item + i
        sheet.Cells(r, 2).WrapText = True
        for c in (3, 5):
            if sheet.Cells(r, c).NumberFormat == "General":
                sheet.Cells(r, c).NumberFormat = money
        write.value(sheet.Cells(r, 2), line.text)
        write.value(sheet.Cells(r, 3), line.unit_price)
        write.value(sheet.Cells(r, 4), line.quantity)
        write.formula(sheet.Cells(r, 5), f"=C{r}*D{r}")
        # The template's height, or more if the description needs it: a line extra,
        # as the PDF can wrap one line more than Excel measures
        designed = sheet.Rows(r).RowHeight
        sheet.Rows(r).AutoFit()
        sheet.Rows(r).RowHeight = max(designed, sheet.Rows(r).RowHeight + 16)
    last_item = first_item + wanted - 1

    labels = _labels(sheet)  # rows moved
    sub, _ = _find(labels, "SUBTOTAL")
    disc, _ = _find(labels, "DISCOUNT")
    rate, _ = _find(labels, "(TAX RATE)", "TAX RATE")
    tax, _ = _find(labels, "TAX")
    total, _ = _find(labels, "TOTAL")

    write.formula(sheet.Cells(sub, 5), f"=SUM(E{first_item}:E{last_item})")
    write.value(sheet.Cells(disc, 5), quote.discount)
    if quote.shipping:
        # Shipping goes before the tax (the tax includes it): the tax rows move down
        # one, into the empty row above TOTAL
        if tax + 1 >= total:
            raise QuoteError(
                "The template needs an empty row between TAX and TOTAL for shipping."
            )
        ship, rate, tax = rate, tax, tax + 1
        sheet.Range(f"D{tax}:E{tax}").UnMerge()
        sheet.Range(f"D{rate}:E{rate}").Copy(sheet.Range(f"D{tax}:E{tax}"))
        sheet.Cells(ship, 4).Value2 = "SHIPPING"
        sheet.Cells(rate, 4).Value2 = "(TAX RATE)"
        sheet.Cells(tax, 4).Value2 = "TAX"
        sheet.Cells(ship, 5).NumberFormat = money
        sheet.Cells(tax, 5).NumberFormat = money
        write.value(sheet.Cells(ship, 5), quote.shipping)
        tax_formula = f"=ROUND((E{sub}-E{disc}+E{ship})*E{rate},2)"
        total_formula = f"=E{sub}-E{disc}+E{ship}+E{tax}"
    else:  # exactly as the template has them
        tax_formula = f"=(E{sub}-E{disc})*E{rate}"
        total_formula = f"=E{sub}-E{disc}+E{tax}"
    sheet.Cells(rate, 5).NumberFormat = (
        "0%" if float(quote.tax_rate).is_integer() else "0.0%"
    )
    write.value(sheet.Cells(rate, 5), quote.tax_rate / 100)
    write.formula(sheet.Cells(tax, 5), tax_formula)
    write.formula(sheet.Cells(total, 5), total_formula)

    # Special notes, only if any: the box under its header, next to the totals
    if notes_text := quote.full_notes():
        notes = sheet.Cells(sub + 1, 2)
        notes.WrapText = True
        notes.VerticalAlignment = -4160  # top
        write.value(notes, notes_text)

    # One page, portrait, everything printed
    last_row = sheet.UsedRange.Row + sheet.UsedRange.Rows.Count - 1
    excel.PrintCommunication = False
    setup = sheet.PageSetup
    setup.PrintArea = f"$A$1:$F${last_row}"
    setup.Orientation = 1  # portrait
    setup.Zoom = False
    setup.FitToPagesWide = 1
    setup.FitToPagesTall = 1
    setup.CenterHorizontally = True
    excel.PrintCommunication = True
    if live:
        with contextlib.suppress(Exception):
            excel.Goto(sheet.Range("A1"), True)  # the whole quotation in view
