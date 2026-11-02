"""Everything else in Word, Excel and PowerPoint beyond changing text (office.py):
formatting, tables, charts, images, slides, sheets. Same direct control (COM), on the
same worker thread, so no clicking through the ribbon.

office_do(app, op, options): options are all text, as the voice model sends them.
Numbers are points in Word and PowerPoint. Colours are "#RRGGBB" or a plain name.
Tables are JSON, a list of rows: [["Item", "Qty"], ["Gateway", "150"]].
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from office import OfficeError, _address, _as_stored, _suppress_com, _word_find

COLOURS = {
    "black": "#000000",
    "white": "#FFFFFF",
    "red": "#C00000",
    "green": "#00B050",
    "blue": "#2F6BFF",
    "yellow": "#FFFF00",
    "orange": "#ED7D31",
    "purple": "#7030A0",
    "grey": "#808080",
    "gray": "#808080",
}
IMAGE_TYPES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".svg",
    ".emf",
    ".wmf",
}
CHARTS = {"column": 51, "bar": 57, "line": 4, "pie": 5, "area": 1, "scatter": -4169}
# wdAlign / xlHAlign / ppAlign
WORD_ALIGN = {"left": 0, "center": 1, "right": 2, "justify": 3}
EXCEL_ALIGN = {"left": -4131, "center": -4108, "right": -4152}
PPT_ALIGN = {"left": 1, "center": 2, "right": 3, "justify": 4}
# ppLayout
PPT_LAYOUTS = {
    "title": 1,
    "content": 2,
    "two_content": 29,
    "title_only": 11,
    "blank": 12,
}


def is_yes(value) -> bool:
    return str(value).strip().casefold() in {"yes", "true", "1", "on"}


def _number(options: dict, name: str, default=None):
    if name not in options or options[name] == "":
        if default is None:
            raise OfficeError(f"Give {name}.")
        return default
    try:
        number = float(options[name])
    except ValueError as exc:
        raise OfficeError(f"{name} must be a number, not {options[name]!r}.") from exc
    return int(number) if number.is_integer() else number


def _text(options: dict, name: str) -> str:
    value = str(options.get(name, "")).strip()
    if not value:
        raise OfficeError(f"Give {name}.")
    return value


def bgr(colour: str) -> int:
    """Office's colour number (blue, green, red) from "#RRGGBB" or a plain name."""
    code = COLOURS.get(colour.strip().casefold(), colour.strip()).lstrip("#")
    try:
        red, green, blue = (int(code[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError as exc:
        raise OfficeError(
            f"{colour!r} is not a colour; use #RRGGBB or a name like red."
        ) from exc
    if len(code) != 6:
        raise OfficeError(
            f"{colour!r} is not a colour; use #RRGGBB or a name like red."
        )
    return blue * 65536 + green * 256 + red


def table_rows(options: dict) -> list[list[str]]:
    try:
        rows = json.loads(_text(options, "rows"))
    except ValueError as exc:
        raise OfficeError(
            'rows must be JSON, like [["Item", "Qty"], ["Gateway", "150"]].'
        ) from exc
    if not (
        isinstance(rows, list) and rows and all(isinstance(r, list) and r for r in rows)
    ):
        raise OfficeError(
            'rows must be JSON, like [["Item", "Qty"], ["Gateway", "150"]].'
        )
    return [[str(cell) for cell in row] for row in rows]


def image_path(options: dict) -> str:
    path = Path(_text(options, "path"))
    if path.suffix.lower() not in IMAGE_TYPES:
        raise OfficeError(f"{path.name} is not a picture.")
    if not path.is_file():
        raise OfficeError(f"There is no file {path}.")
    return str(path.resolve())


def _choice(table: dict, options: dict, name: str):
    value = str(options[name]).strip().casefold()
    if value not in table:
        raise OfficeError(f"{name} must be one of: {', '.join(table)}.")
    return table[value]


def _font(font, options: dict, *, true=True, colour=None) -> None:
    """The font settings all three apps share. ``colour`` sets the colour."""
    if "bold" in options:
        font.Bold = true if is_yes(options["bold"]) else 0
    if "italic" in options:
        font.Italic = true if is_yes(options["italic"]) else 0
    if "size" in options:
        font.Size = _number(options, "size")
    if "font" in options:
        font.Name = _text(options, "font")
    if "color" in options:
        (colour or (lambda c: setattr(font, "Color", c)))(bgr(options["color"]))


# --- Word ---------------------------------------------------------------------------


def _word_target(doc, options: dict):
    """The text an op works on: the first match of find, or a whole paragraph."""
    from office import Office

    if options.get("find"):
        actual = _as_stored(doc.Content.Text, str(options["find"]))
        if actual is None:
            raise OfficeError(f"{options['find']!r} is not in the document.")
        found = doc.Content
        if not _word_find(
            found, actual.replace(chr(13), "^p").replace(chr(11), "^l")[:255]
        ):
            raise OfficeError(f"{options['find']!r} is not in the document.")
        return found
    return Office._word_paragraph(doc, _number(options, "paragraph"))


def _word_format(_application, doc, options):
    target = _word_target(doc, options)
    _font(target.Font, options, true=1)
    if "underline" in options:
        target.Font.Underline = 1 if is_yes(options["underline"]) else 0
    if "highlight" in options:
        target.HighlightColorIndex = 7 if is_yes(options["highlight"]) else 0  # yellow
    if "style" in options:
        target.Style = _text(options, "style")  # e.g. Heading 1
    if "align" in options:
        target.ParagraphFormat.Alignment = _choice(WORD_ALIGN, options, "align")
    return {"formatted": target.Text[:80]}


def _new_paragraph_after(doc, paragraph: int):
    """An empty paragraph after this one (0: at the very start)."""
    if paragraph == 0:
        rng = doc.Paragraphs(1).Range
        rng.InsertParagraphBefore()
        return doc.Paragraphs(1).Range
    if not 1 <= paragraph <= doc.Paragraphs.Count:
        raise OfficeError(
            f"There is no paragraph {paragraph}; the document has {doc.Paragraphs.Count}."
        )
    doc.Paragraphs(paragraph).Range.InsertParagraphAfter()
    return doc.Paragraphs(paragraph + 1).Range


def _word_insert_table(_application, doc, options):
    rows = table_rows(options)
    columns = max(len(r) for r in rows)
    place = _new_paragraph_after(
        doc, _number(options, "paragraph", doc.Paragraphs.Count)
    )
    table = doc.Tables.Add(place, len(rows), columns)
    with _suppress_com():
        table.Style = "Table Grid"
    for r, row in enumerate(rows, 1):
        for c, value in enumerate(row, 1):
            table.Cell(r, c).Range.Text = value
    return {"table_rows": len(rows), "table_columns": columns}


def _word_insert_image(_application, doc, options):
    path = image_path(options)
    place = _new_paragraph_after(
        doc, _number(options, "paragraph", doc.Paragraphs.Count)
    )
    picture = doc.InlineShapes.AddPicture(path, False, True, place)
    if "width" in options:
        picture.LockAspectRatio = -1
        picture.Width = _number(options, "width")
    return {"inserted": Path(path).name}


def _word_delete_paragraph(_application, doc, options):
    paragraph = _number(options, "paragraph")
    if not 1 <= paragraph <= doc.Paragraphs.Count:
        raise OfficeError(
            f"There is no paragraph {paragraph}; the document has {doc.Paragraphs.Count}."
        )
    doc.Paragraphs(paragraph).Range.Delete()
    return {"deleted_paragraph": paragraph}


def _word_page_break(_application, doc, options):
    place = _new_paragraph_after(
        doc, _number(options, "paragraph", doc.Paragraphs.Count)
    )
    place.InsertBreak(7)  # wdPageBreak
    return {"page_break": True}


def _word_list(doc, options, numbered: bool):
    first = _number(options, "paragraph")
    last = _number(options, "last_paragraph", first)
    if not 1 <= first <= last <= doc.Paragraphs.Count:
        raise OfficeError(f"The document has {doc.Paragraphs.Count} paragraphs.")
    rng = doc.Range(doc.Paragraphs(first).Range.Start, doc.Paragraphs(last).Range.End)
    if numbered:
        rng.ListFormat.ApplyNumberDefault()
    else:
        rng.ListFormat.ApplyBulletDefault()
    return {"list_paragraphs": [first, last]}


def _word_bullets(_application, doc, options):
    return _word_list(doc, options, numbered=False)


def _word_numbering(_application, doc, options):
    return _word_list(doc, options, numbered=True)


def _word_accept_changes(_application, doc, _options):
    count = doc.Revisions.Count
    doc.Revisions.AcceptAll()
    return {"accepted": count}


def _word_reject_changes(_application, doc, _options):
    count = doc.Revisions.Count
    doc.Revisions.RejectAll()
    return {"rejected": count}


WORD_OPS = {
    "format": _word_format,
    "insert_table": _word_insert_table,
    "insert_image": _word_insert_image,
    "delete_paragraph": _word_delete_paragraph,
    "page_break": _word_page_break,
    "bullets": _word_bullets,
    "numbering": _word_numbering,
    "accept_changes": _word_accept_changes,
    "reject_changes": _word_reject_changes,
}


# --- Excel --------------------------------------------------------------------------


def _excel_sheet_for(application, options):
    from office import Office

    return Office._excel_sheet(application, str(options.get("sheet", "")))


def _excel_format(application, _doc, options):
    _, ws = _excel_sheet_for(application, options)
    rng = ws.Range(_text(options, "range"))
    _font(rng.Font, options)
    if "fill" in options:
        rng.Interior.Color = bgr(options["fill"])
    if "number_format" in options:
        rng.NumberFormat = _text(options, "number_format")  # e.g. #,##0.00
    if "align" in options:
        rng.HorizontalAlignment = _choice(EXCEL_ALIGN, options, "align")
    if "wrap" in options:
        rng.WrapText = is_yes(options["wrap"])
    if "column_width" in options:
        rng.ColumnWidth = _number(options, "column_width")
    if "border" in options and is_yes(options["border"]):
        rng.Borders.LineStyle = 1  # xlContinuous
    return {"formatted": _address(rng)}


def _excel_rows_or_columns(application, options, kind: str, delete: bool):
    _, ws = _excel_sheet_for(application, options)
    where = _text(options, kind[:-1])  # row or column
    count = int(_number(options, "count", 1))
    if kind == "rows":
        first = int(where)
        block = ws.Rows(f"{first}:{first + count - 1}")
    else:
        first = ws.Range(f"{where}1").Column
        block = ws.Range(
            ws.Cells(1, first), ws.Cells(1, first + count - 1)
        ).EntireColumn
    block.Delete() if delete else block.Insert()
    return {"deleted" if delete else "inserted": f"{count} {kind} at {where}"}


def _excel_insert_rows(application, _doc, options):
    return _excel_rows_or_columns(application, options, "rows", delete=False)


def _excel_delete_rows(application, _doc, options):
    return _excel_rows_or_columns(application, options, "rows", delete=True)


def _excel_insert_columns(application, _doc, options):
    return _excel_rows_or_columns(application, options, "columns", delete=False)


def _excel_delete_columns(application, _doc, options):
    return _excel_rows_or_columns(application, options, "columns", delete=True)


def _excel_add_sheet(application, _doc, options):
    workbook, _ = _excel_sheet_for(application, {})
    sheet = workbook.Worksheets.Add(
        After=workbook.Worksheets(workbook.Worksheets.Count)
    )
    if options.get("name"):
        sheet.Name = _text(options, "name")
    return {"added_sheet": sheet.Name}


def _excel_rename_sheet(application, _doc, options):
    _, ws = _excel_sheet_for(application, options)
    ws.Name = _text(options, "name")
    return {"renamed_sheet": ws.Name}


def _excel_delete_sheet(application, _doc, options):
    _, ws = _excel_sheet_for(application, {"sheet": _text(options, "sheet")})
    name = ws.Name
    application.DisplayAlerts = False  # the gatekeeper has already asked the user
    try:
        ws.Delete()
    finally:
        application.DisplayAlerts = True
    return {"deleted_sheet": name}


def _excel_sort(application, _doc, options):
    _, ws = _excel_sheet_for(application, options)
    rng = ws.Range(_text(options, "range"))
    order = 2 if is_yes(options.get("descending", "")) else 1
    header = 2 if str(options.get("header", "yes")).casefold() == "no" else 1
    rng.Sort(Key1=ws.Range(_text(options, "key")), Order1=order, Header=header)
    return {"sorted": _address(rng)}


def _excel_filter(application, _doc, options):
    _, ws = _excel_sheet_for(application, options)
    rng = ws.Range(_text(options, "range"))
    rng.AutoFilter()
    return {"filter_toggled": _address(rng)}


def _excel_autofit(application, _doc, options):
    _, ws = _excel_sheet_for(application, options)
    rng = ws.Range(options["range"]) if options.get("range") else ws.UsedRange
    rng.Columns.AutoFit()
    return {"autofit": _address(rng)}


def _excel_merge(application, _doc, options):
    _, ws = _excel_sheet_for(application, options)
    rng = ws.Range(_text(options, "range"))
    rng.Merge()
    return {"merged": _address(rng)}


def _excel_chart(application, _doc, options):
    _, ws = _excel_sheet_for(application, options)
    rng = ws.Range(_text(options, "range"))
    kind = _choice(CHARTS, {"type": options.get("type", "column")}, "type")
    used = ws.UsedRange
    left = used.Left + used.Width + 20  # beside the data
    shape = ws.Shapes.AddChart2(-1, kind, left, used.Top, 420, 260)
    shape.Chart.SetSourceData(rng)
    if options.get("title"):
        shape.Chart.HasTitle = True
        shape.Chart.ChartTitle.Text = _text(options, "title")
    return {"chart": shape.Name, "data": _address(rng)}


EXCEL_OPS = {
    "format": _excel_format,
    "insert_rows": _excel_insert_rows,
    "delete_rows": _excel_delete_rows,
    "insert_columns": _excel_insert_columns,
    "delete_columns": _excel_delete_columns,
    "add_sheet": _excel_add_sheet,
    "rename_sheet": _excel_rename_sheet,
    "delete_sheet": _excel_delete_sheet,
    "sort": _excel_sort,
    "filter": _excel_filter,
    "autofit": _excel_autofit,
    "merge": _excel_merge,
    "chart": _excel_chart,
}


# --- PowerPoint ---------------------------------------------------------------------


def _ppt_slide(pres, options, name="slide"):
    number = int(_number(options, name))
    if not 1 <= number <= pres.Slides.Count:
        raise OfficeError(
            f"There is no slide {number}; the deck has {pres.Slides.Count} slides."
        )
    return pres.Slides(number)


def _ppt_show(application, slide) -> None:
    with _suppress_com():
        application.ActiveWindow.View.GotoSlide(slide.SlideIndex)


def _ppt_add_slide(application, pres, options):
    position = int(_number(options, "position", pres.Slides.Count + 1))
    if not 1 <= position <= pres.Slides.Count + 1:
        raise OfficeError(f"The deck has {pres.Slides.Count} slides.")
    layout = _choice(
        PPT_LAYOUTS, {"layout": options.get("layout", "content")}, "layout"
    )
    slide = pres.Slides.Add(position, layout)
    if options.get("title") and slide.Shapes.HasTitle:
        slide.Shapes.Title.TextFrame.TextRange.Text = str(options["title"])
    if options.get("body"):
        for i in range(1, slide.Shapes.Placeholders.Count + 1):
            placeholder = slide.Shapes.Placeholders(i)
            if placeholder.HasTextFrame and placeholder.Name != (
                slide.Shapes.Title.Name if slide.Shapes.HasTitle else ""
            ):
                placeholder.TextFrame.TextRange.Text = str(options["body"])
                break
    _ppt_show(application, slide)
    return {"slide": slide.SlideIndex, "total_slides": pres.Slides.Count}


def _ppt_delete_slide(_application, pres, options):
    slide = _ppt_slide(pres, options)
    number = slide.SlideIndex
    slide.Delete()
    return {"deleted_slide": number, "total_slides": pres.Slides.Count}


def _ppt_duplicate_slide(application, pres, options):
    copy = _ppt_slide(pres, options).Duplicate()
    _ppt_show(application, copy(1))
    return {"new_slide": copy(1).SlideIndex, "total_slides": pres.Slides.Count}


def _ppt_move_slide(application, pres, options):
    slide = _ppt_slide(pres, options)
    to = int(_number(options, "to"))
    if not 1 <= to <= pres.Slides.Count:
        raise OfficeError(f"The deck has {pres.Slides.Count} slides.")
    slide.MoveTo(to)
    _ppt_show(application, slide)
    return {"moved_to": slide.SlideIndex}


def _ppt_box(options: dict, width=400, height=100) -> tuple:
    return (
        _number(options, "left", 60),
        _number(options, "top", 60),
        _number(options, "width", width),
        _number(options, "height", height),
    )


def _ppt_text_format(text_range, options: dict) -> None:
    _font(
        text_range.Font,
        options,
        true=-1,
        colour=lambda c: setattr(text_range.Font.Color, "RGB", c),
    )
    if "align" in options:
        text_range.ParagraphFormat.Alignment = _choice(PPT_ALIGN, options, "align")


def _ppt_add_textbox(application, pres, options):
    slide = _ppt_slide(pres, options)
    box = slide.Shapes.AddTextbox(1, *_ppt_box(options))
    box.TextFrame.TextRange.Text = _text(options, "text")
    _ppt_text_format(box.TextFrame.TextRange, options)
    _ppt_show(application, slide)
    return {"slide": slide.SlideIndex, "shape": box.Name}


def _ppt_format(application, pres, options):
    from office import Office

    slide = _ppt_slide(pres, options)
    shape = Office._ppt_shape(pres, slide.SlideIndex, _text(options, "shape"))
    _ppt_text_format(shape.TextFrame.TextRange, options)
    _ppt_show(application, slide)
    return {"slide": slide.SlideIndex, "formatted": shape.Name}


def _ppt_move_shape(application, pres, options):
    from office import Office

    slide = _ppt_slide(pres, options)
    shape = Office._ppt_shape(pres, slide.SlideIndex, _text(options, "shape"))
    for name, attribute in (
        ("left", "Left"),
        ("top", "Top"),
        ("width", "Width"),
        ("height", "Height"),
    ):
        if name in options:
            setattr(shape, attribute, _number(options, name))
    _ppt_show(application, slide)
    return {"slide": slide.SlideIndex, "moved": shape.Name}


def _ppt_delete_shape(_application, pres, options):
    from office import Office

    slide = _ppt_slide(pres, options)
    shape = Office._ppt_shape(pres, slide.SlideIndex, _text(options, "shape"))
    name = shape.Name
    shape.Delete()
    return {"slide": slide.SlideIndex, "deleted": name}


def _ppt_add_image(application, pres, options):
    slide = _ppt_slide(pres, options)
    picture = slide.Shapes.AddPicture(
        image_path(options),
        0,
        -1,
        _number(options, "left", 60),
        _number(options, "top", 60),
    )
    if "width" in options:
        picture.LockAspectRatio = -1
        picture.Width = _number(options, "width")
    _ppt_show(application, slide)
    return {"slide": slide.SlideIndex, "shape": picture.Name}


def _ppt_add_table(application, pres, options):
    slide = _ppt_slide(pres, options)
    rows = table_rows(options)
    columns = max(len(r) for r in rows)
    shape = slide.Shapes.AddTable(
        len(rows), columns, *_ppt_box(options, 600, 30 * len(rows))
    )
    for r, row in enumerate(rows, 1):
        for c, value in enumerate(row, 1):
            shape.Table.Cell(r, c).Shape.TextFrame.TextRange.Text = value
    _ppt_show(application, slide)
    return {"slide": slide.SlideIndex, "shape": shape.Name}


def _ppt_set_notes(_application, pres, options):
    slide = _ppt_slide(pres, options)
    slide.NotesPage.Shapes.Placeholders(2).TextFrame.TextRange.Text = _text(
        options, "text"
    )
    return {"slide": slide.SlideIndex, "notes": True}


def _ppt_start_show(application, pres, options):
    window = pres.SlideShowSettings.Run()
    if options.get("slide"):
        window.View.GotoSlide(int(_number(options, "slide")))
    return {"slide_show": True, "slide": window.View.Slide.SlideIndex}


def _ppt_end_show(application, _pres, _options):
    if application.SlideShowWindows.Count:
        application.SlideShowWindows(1).View.Exit()
    return {"slide_show": False}


PPT_OPS = {
    "add_slide": _ppt_add_slide,
    "delete_slide": _ppt_delete_slide,
    "duplicate_slide": _ppt_duplicate_slide,
    "move_slide": _ppt_move_slide,
    "add_textbox": _ppt_add_textbox,
    "format": _ppt_format,
    "move_shape": _ppt_move_shape,
    "delete_shape": _ppt_delete_shape,
    "add_image": _ppt_add_image,
    "add_table": _ppt_add_table,
    "set_notes": _ppt_set_notes,
    "start_show": _ppt_start_show,
    "end_show": _ppt_end_show,
}

OPS = {"word": WORD_OPS, "excel": EXCEL_OPS, "powerpoint": PPT_OPS}


# --- Files --------------------------------------------------------------------------

# File type -> Office's format number, per app. PDF is exported, not "saved as".
SAVE_FORMATS = {
    "word": {".docx": 16, ".doc": 0, ".rtf": 6, ".txt": 2, ".pdf": None},
    "excel": {".xlsx": 51, ".xls": 56, ".csv": 6, ".pdf": None},
    "powerpoint": {".pptx": 24, ".ppt": 1, ".pdf": 32},
}


def save_as(application, app: str, document, path: str, overwrite: bool) -> dict:
    """A copy under a new name or type. A PDF leaves the document as it was."""
    target = Path(os.path.expandvars(os.path.expanduser(path)))
    if not target.is_absolute():
        target = Path.home() / "Documents" / target
    formats = SAVE_FORMATS[app]
    suffix = target.suffix.lower()
    if suffix not in formats:
        raise OfficeError(f"A {app} file can be saved as: {', '.join(formats)}.")
    if not target.parent.is_dir():
        raise OfficeError(f"There is no folder {target.parent}.")
    if target.exists() and not overwrite:
        raise OfficeError(
            f"{target} already exists: ask the user whether to replace it."
        )
    name = str(target)
    if app == "word":
        if suffix == ".pdf":
            document.ExportAsFixedFormat(name, 17)  # wdExportFormatPDF
        else:
            document.SaveAs2(name, formats[suffix])
    elif app == "excel":
        application.DisplayAlerts = False  # the user already agreed to replace it
        try:
            if suffix == ".pdf":
                document.ExportAsFixedFormat(0, name)  # xlTypePDF
            else:
                document.SaveAs(name, formats[suffix])
        finally:
            application.DisplayAlerts = True
    elif suffix == ".pdf":
        document.SaveCopyAs(name, 32)  # ppSaveAsPDF
    else:
        document.SaveAs(name, formats[suffix])
    return {"saved_as": name}


def close(app: str, document, save: str) -> dict:
    """Close one file (never the app). ``save``: "yes", "no"; "" refuses to lose work."""
    name = document.Name
    if not document.Saved and save not in ("yes", "no"):
        raise OfficeError(
            f"{name} has unsaved changes: ask the user to save them or not."
        )
    if save == "yes":
        document.Save()
    if app == "powerpoint":
        document.Saved = True  # PowerPoint would otherwise ask on screen
        document.Close()
    elif app == "word":
        document.Close(0)  # wdDoNotSaveChanges: saved above if wanted
    else:
        document.Close(False)
    return {"closed": name}
