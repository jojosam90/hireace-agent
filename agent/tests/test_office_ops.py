"""office_do and friends: the rules without Office, and (HIREACE_TEST_OFFICE=1, with no
Office app open) against the real Word, Excel and PowerPoint, on temporary files."""

import os
import subprocess
from pathlib import Path

import pytest
from PIL import Image
from test_gatekeeper import FakeBrowser

import office_ops
from gatekeeper import Gatekeeper
from office import Office, OfficeError
from policy import ALLOW, ASK, DENY, PageContext, decide


def verdict(action, args):
    return decide(action, args, PageContext()).verdict


def test_edits_are_free_and_what_loses_work_asks():
    assert verdict("office_new", {"app": "word"}) == ALLOW
    assert verdict("office_do", {"app": "word", "op": "format", "options": {}}) == ALLOW
    assert verdict("office_do", {"app": "excel", "op": "delete_sheet"}) == ASK
    assert verdict("office_save_as", {"path": r"C:\x\a.docx"}) == ASK
    assert verdict("office_close", {"save": "no"}) == ASK


def test_no_programs_or_card_numbers():
    picture = {
        "app": "word",
        "op": "insert_image",
        "options": {"path": r"C:\x\run.exe"},
    }
    assert verdict("office_do", picture) == DENY
    assert verdict("office_save_as", {"path": r"C:\x\a.xlsm"}) == DENY
    card = {"app": "excel", "op": "format", "options": {"text": "4111 1111 1111 1111"}}
    assert verdict("office_do", card) == DENY


class Recording:
    def __init__(self):
        self.calls = []

    async def run(self, action, args):
        self.calls.append(action)
        return {"ok": True}


async def test_an_earlier_approval_does_not_cover_what_loses_work(tmp_path):
    office = Recording()
    gk = Gatekeeper(FakeBrowser(), office=office, audit_path=tmp_path / "a.jsonl")
    gk._approved_sessions.add("call")

    saved_close = await gk.submit(
        "call", "office_close", {"app": "word", "save": "yes"}
    )
    assert saved_close["status"] == "done"

    # Nothing is saved or lost on an earlier approval
    for action, args in [
        ("office_save", {"app": "excel"}),
        ("office_save_as", {"app": "word", "path": "a.docx"}),
        ("office_close", {"app": "word", "save": "no"}),
        ("office_save_as", {"app": "word", "path": "a.docx", "overwrite": True}),
        (
            "office_do",
            {"app": "excel", "op": "delete_sheet", "options": {"sheet": "S"}},
        ),
    ]:
        assert (await gk.submit("call", action, args))["status"] == "needs_approval"


def test_colours_and_tables_are_checked():
    assert office_ops.bgr("#FF0000") == 0x0000FF
    assert office_ops.bgr("blue") == office_ops.bgr("#2F6BFF")
    with pytest.raises(OfficeError, match="not a colour"):
        office_ops.bgr("sparkly")
    assert office_ops.table_rows({"rows": '[["a", 1]]'}) == [["a", "1"]]
    with pytest.raises(OfficeError, match="rows must be JSON"):
        office_ops.table_rows({"rows": "a,b"})


def test_every_op_says_what_exists_in_the_tool_description():
    from office_tools import OfficeTools

    text = OfficeTools.office_do.__doc__ or ""
    for ops in office_ops.OPS.values():
        for op in ops:
            assert op in text, op


# --- The real apps ------------------------------------------------------------------


def _running_office() -> list[str]:
    names = ["WINWORD.EXE", "EXCEL.EXE", "POWERPNT.EXE"]
    listing = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    return [n for n in names if n in listing]


def doer(office, app):
    def do(op, **options):
        return office.run("office_do", {"app": app, "op": op, "options": options})

    return do


@pytest.fixture
async def real_office(tmp_path):
    if os.environ.get("HIREACE_TEST_OFFICE") != "1":
        pytest.skip("set HIREACE_TEST_OFFICE=1 to use the real Office apps")
    # They attach to whatever is running: never to the user's open documents
    if _running_office():
        pytest.skip(f"Office is open: {_running_office()}")
    office = Office()
    yield office

    def quit_all():
        import win32com.client

        for prog_id, files in (
            ("Word.Application", "Documents"),
            ("Excel.Application", "Workbooks"),
            ("PowerPoint.Application", "Presentations"),
        ):
            try:
                app = win32com.client.GetActiveObject(prog_id)
            except Exception:
                continue
            opened = getattr(app, files)
            for i in range(opened.Count, 0, -1):
                if prog_id.startswith("Power"):
                    opened(i).Saved = True
                    opened(i).Close()
                elif prog_id.startswith("Word"):
                    opened(i).Close(0)
                else:
                    opened(i).Close(False)
            app.Quit()

    import asyncio

    await asyncio.get_running_loop().run_in_executor(office._thread, quit_all)


@pytest.fixture
def picture(tmp_path) -> str:
    path = tmp_path / "logo.png"
    Image.new("RGB", (60, 40), "#2F6BFF").save(path)
    return str(path)


async def test_word_for_real(real_office, tmp_path, picture):
    office = real_office
    await office.run("office_new", {"app": "word"})
    do = doer(office, "word")

    await office.run("word_edit", {"paragraph": 1, "text": "Quarterly report"})
    await do(
        "format", paragraph="1", bold="yes", size="20", color="blue", style="Heading 1"
    )
    await do("insert_table", paragraph="1", rows='[["Item","Qty"],["Gateway","150"]]')
    await do("insert_image", path=picture, width="50")
    await do("page_break")
    await do("accept_changes")

    read = await office.run("office_read", {"app": "word"})
    assert read["paragraphs"][0]["text"] == "Quarterly report"
    assert any("Gateway" in p["text"] for p in read["paragraphs"])

    docx = tmp_path / "report.docx"
    pdf = tmp_path / "report.pdf"
    await office.run("office_save_as", {"app": "word", "path": str(docx)})
    await office.run("office_save_as", {"app": "word", "path": str(pdf)})
    assert docx.stat().st_size > 1000 and pdf.read_bytes().startswith(b"%PDF")
    with pytest.raises(OfficeError, match="already exists"):
        await office.run("office_save_as", {"app": "word", "path": str(docx)})
    await office.run("office_close", {"app": "word"})


async def test_excel_for_real(real_office, tmp_path):
    office = real_office
    await office.run("office_new", {"app": "excel"})
    do = doer(office, "excel")

    await office.run(
        "excel_set_cells",
        {
            "cells": {
                "A1": "Item",
                "B1": "Qty",
                "A2": "Sensor",
                "B2": "80",
                "A3": "Gateway",
                "B3": "150",
            }
        },
    )
    await do("format", range="A1:B1", bold="yes", fill="#DDEEFF", border="yes")
    await do("format", range="B2:B3", number_format="#,##0")
    await do("sort", range="A1:B3", key="B2", descending="yes")
    await do("insert_rows", row="2", count="1")
    await do("delete_rows", row="2")
    await do("insert_columns", column="C", count="1")
    await do("delete_columns", column="C")
    await do("autofit")
    chart = await do("chart", range="A1:B3", type="column", title="Units")
    await do("add_sheet", name="Notes")
    await do("rename_sheet", sheet="Notes", name="Remarks")
    await do("delete_sheet", sheet="Remarks")

    read = await office.run("office_read", {"app": "excel"})
    assert chart["data"] == "A1:B3"
    assert read["rows"][1][0] == "Gateway"  # sorted by quantity, largest first
    assert len(read["sheets"]) == 1

    book = tmp_path / "units.xlsx"
    await office.run("office_save_as", {"app": "excel", "path": str(book)})
    await office.run(
        "office_save_as", {"app": "excel", "path": str(tmp_path / "units.pdf")}
    )
    assert book.exists() and (tmp_path / "units.pdf").exists()
    await office.run("excel_set_cells", {"cells": {"A9": "unsaved"}})
    with pytest.raises(OfficeError, match="unsaved changes"):
        await office.run("office_close", {"app": "excel"})
    await office.run("office_close", {"app": "excel", "save": "no"})


async def test_powerpoint_for_real(real_office, tmp_path, picture):
    office = real_office
    await office.run("office_new", {"app": "powerpoint"})
    do = doer(office, "powerpoint")

    second = await do("add_slide", title="Results", body="Sales are up")
    assert second["slide"] == 2
    await do("add_slide", layout="blank")
    box = await do(
        "add_textbox", slide="3", text="Hello", size="28", bold="yes", color="red"
    )
    await do("format", slide="3", shape=box["shape"], italic="yes", align="center")
    await do("move_shape", slide="3", shape=box["shape"], left="100", top="120")
    await do("add_image", slide="3", path=picture, width="80")
    await do("add_table", slide="3", rows='[["Item","Qty"],["Gateway","150"]]')
    await do("set_notes", slide="2", text="Mention the new customers")
    copied = await do("duplicate_slide", slide="2")
    await do("move_slide", slide=str(copied["new_slide"]), to="4")
    await do("delete_slide", slide="4")
    await do("delete_shape", slide="3", shape=box["shape"])

    read = await office.run("office_read", {"app": "powerpoint"})
    assert read["total_slides"] == 3
    assert any(s["text"] == "Results" for s in read["slides"][1]["shapes"])

    deck = tmp_path / "deck.pptx"
    pdf = tmp_path / "deck.pdf"
    await office.run("office_save_as", {"app": "powerpoint", "path": str(deck)})
    await office.run("office_save_as", {"app": "powerpoint", "path": str(pdf)})
    assert Path(deck).exists() and pdf.read_bytes().startswith(b"%PDF")
    await office.run("office_close", {"app": "powerpoint"})


async def test_changing_excel_values_in_their_own_cells_for_real(real_office, tmp_path):
    office = real_office
    await office.run("office_new", {"app": "excel"})
    book = tmp_path / "prices.xlsx"
    cells = {
        "A1": "Item",
        "B1": "Qty",
        "C1": "Price",
        "D1": "Amount",
        "A2": "Gateway",
        "B2": "150",
        "C2": "62.6",
        "D2": "=B2*C2",
        "A3": "Sensor",
        "B3": "450",
        "C3": "62.6",
        "D3": "=B3*C3",
    }
    await office.run("excel_set_cells", {"cells": cells})
    do = doer(office, "excel")
    await do("format", range="C2:C3", number_format="#,##0.00", fill="#DDEEFF")
    await office.run("office_save_as", {"app": "excel", "path": str(book)})
    on_disk = book.read_bytes()

    def state():
        import win32com.client

        excel = win32com.client.GetActiveObject("Excel.Application")
        ws = excel.ActiveSheet
        return {
            "saved": bool(excel.ActiveWorkbook.Saved),
            "alerts": bool(excel.DisplayAlerts),
            "b2": ws.Range("B2").Value,
            "d2": ws.Range("D2").Value,
            "d2_formula": ws.Range("D2").Formula,
            "c2_format": ws.Range("C2").NumberFormat,
            "c2_fill": ws.Range("C2").Interior.Color,
            "c3": ws.Range("C3").Value,
        }

    async def now():
        import asyncio

        return await asyncio.get_running_loop().run_in_executor(office._thread, state)

    fill_before = (await now())["c2_fill"]

    # One clear match: changed where it is, and the total follows
    result = await office.run("excel_replace", {"old": "150", "new": "200"})
    assert result["changed"] == [{"cell": "B2", "old": 150, "new": 200}]
    after = await now()
    assert after["b2"] == 200 and after["d2"] == 200 * 62.6
    # Nothing saved, and Excel will still ask when the user closes it
    assert after["saved"] is False and after["alerts"] is True
    assert book.read_bytes() == on_disk

    # Several matches: nothing changes until the user says which
    with pytest.raises(OfficeError, match="in 2 cells: C2, C3"):
        await office.run("excel_replace", {"old": "62.6", "new": "70"})
    assert (await now())["c3"] == 62.6
    result = await office.run(
        "excel_replace", {"old": "62.6", "new": "$1,070.50", "cell": "C2"}
    )
    assert result["changed"][0]["new"] == 1070.5
    after = await now()
    assert (
        after["c2_format"] == "#,##0.00" and after["c2_fill"] == fill_before
    )  # as it was
    assert after["c3"] == 62.6  # the other one untouched

    # The cell does not hold what the user thinks: no blind edit
    with pytest.raises(OfficeError, match="B3 holds 450, not '999'"):
        await office.run("excel_replace", {"old": "999", "new": "1", "cell": "B3"})
    with pytest.raises(OfficeError, match="No cell"):
        await office.run("excel_replace", {"old": "nothing like this", "new": "1"})

    # A formula is never typed over by accident
    formula = (await now())["d2_formula"]
    with pytest.raises(OfficeError, match="calculated by the formula"):
        await office.run(
            "excel_replace", {"old": str((await now())["d2"]), "new": "5", "cell": "D2"}
        )
    with pytest.raises(OfficeError, match="calculated by the formula"):
        await office.run("excel_set_cells", {"cells": {"D2": "5"}})
    assert (await now())["d2_formula"] == formula
    assert book.read_bytes() == on_disk

    # Closing asks; only an explicit answer closes it
    with pytest.raises(OfficeError, match="Save the changes, yes or no"):
        await office.run("office_close", {"app": "excel"})
    await office.run("office_close", {"app": "excel", "save": "no"})
    assert book.read_bytes() == on_disk


async def test_changing_a_quantity_in_a_quotation_draft_for_real(
    real_office, tmp_path, monkeypatch
):
    import quotation

    if not quotation.template_path().is_file():
        pytest.skip("the company's quotation template is not on this PC")
    office = real_office
    monkeypatch.setenv("QUOTE_DIR", str(tmp_path))
    monkeypatch.setenv("QUOTE_PDF_DIR", str(tmp_path))
    monkeypatch.setenv(
        "QUOTE_PRICE_LIST",
        str(Path(__file__).parent.parent / "price_list.example.json"),
    )
    monkeypatch.setattr(quotation, "_drafts", {})
    draft = {
        "customer": "Seaview Hotel",
        "items": [
            {"model": "AC-GW-100", "quantity": 150},
            {"model": "AC-SW-4", "quantity": 450},
        ],
    }

    first = await office.run("make_quotation", dict(draft))
    assert first["total"] == 150 * 60 + 450 * 50

    def read(cell_label):
        import win32com.client

        excel = win32com.client.GetActiveObject("Excel.Application")
        ws = excel.ActiveSheet
        found = ws.UsedRange.Find(cell_label)
        return {
            "total": ws.Cells(found.Row, 5).Value,
            "saved": bool(excel.ActiveWorkbook.Saved),
        }

    async def total():
        import asyncio

        return await asyncio.get_running_loop().run_in_executor(
            office._thread, lambda: read("SUBTOTAL")
        )

    # Changed in its own cell: the totals follow, nothing is written to disk
    result = await office.run("excel_replace", {"old": "150", "new": "200"})
    assert result["changed"][0]["new"] == 200
    after = await total()
    assert after["total"] == 200 * 60 + 450 * 50
    assert list(tmp_path.iterdir()) == []

    # A change never rebuilds the open draft by accident
    with pytest.raises(quotation.QuoteError, match="already open"):
        await office.run("make_quotation", dict(draft))
    assert (await total())["total"] == 200 * 60 + 450 * 50

    # Closed without saving: nothing on disk, and a new draft can be made
    await office.run("office_close", {"app": "excel", "save": "no"})
    assert list(tmp_path.iterdir()) == []
    await office.run("make_quotation", dict(draft))
    await office.run("office_close", {"app": "excel", "save": "no"})
    assert list(tmp_path.iterdir()) == []
