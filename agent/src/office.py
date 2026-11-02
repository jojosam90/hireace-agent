"""Direct control of the user's open Word, Excel and PowerPoint documents (COM).

Much faster and more reliable than clicking around the screen: one call reads a
whole document, jumps to a slide/cell/paragraph, or changes text. Every operation
first leaves Protected View (the "Enable Editing" bar), and edits are highlighted
so the user can see them: Word tracks changes, Excel fills changed cells yellow,
PowerPoint highlights changed text.

Only the gatekeeper uses this. COM objects belong to the thread that created
them, so every call runs on one dedicated worker thread.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import re
import sys
from concurrent.futures import ThreadPoolExecutor

APPS = {
    "word": "Word.Application",
    "excel": "Excel.Application",
    "powerpoint": "PowerPoint.Application",
}
YELLOW = 0x00FFFF  # Office colours are BGR: this is RGB(255, 255, 0)
MAX_TEXT = 300  # characters per paragraph / shape / cell shown to the model


class OfficeError(Exception):
    """A user-facing Office operation failure."""


def _short(text: str) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "…"


def _plain(value):
    if isinstance(value, datetime.datetime):
        return (
            value.strftime("%Y-%m-%d %H:%M")
            if value.time() != datetime.time()
            else value.strftime("%Y-%m-%d")
        )
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


class Office:
    def __init__(self) -> None:
        self._thread = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="office", initializer=self._init_com
        )

    @staticmethod
    def _init_com() -> None:
        if sys.platform == "win32":
            import pythoncom

            pythoncom.CoInitialize()

    async def run(self, action: str, args: dict) -> dict:
        handler = getattr(self, f"_{action}", None)
        if handler is None:
            raise OfficeError(f"Unknown Office action {action!r}.")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._thread, lambda: self._call(handler, args)
        )

    def _call(self, handler, args: dict) -> dict:
        import pywintypes

        try:
            return handler(**args)
        except pywintypes.com_error as exc:
            detail = (
                exc.excepinfo[2] if exc.excepinfo and exc.excepinfo[2] else exc.strerror
            )
            raise OfficeError(f"Office could not do that: {detail}") from exc

    # --- Shared -------------------------------------------------------------------

    def _app(self, app: str, document: str = ""):
        """The running app, out of Protected View, with ``document`` (part of its
        file name) made the active one; without it, the active document."""
        import pywintypes
        import win32com.client

        if app not in APPS:
            raise OfficeError(f"Unknown app {app!r}; use word, excel or powerpoint.")
        try:
            application = win32com.client.GetActiveObject(APPS[app])
        except pywintypes.com_error as exc:
            raise OfficeError(
                f"{app.capitalize()} is not open. Open the file first (find_files, then open_file)."
            ) from exc
        self._enable_editing(application, app, document)
        if document:
            self._activate(application, app, document)
        return application

    @staticmethod
    def _enable_editing(application, app: str, document: str = "") -> None:
        """Leave Protected View: what clicking "Enable Editing" does."""
        attribute = {
            "word": "Document",
            "excel": "Workbook",
            "powerpoint": "Presentation",
        }[app]
        with _suppress_com():
            for i in range(application.ProtectedViewWindows.Count, 0, -1):
                window = application.ProtectedViewWindows(i)
                name = getattr(window, attribute).Name
                if not document or document.casefold() in name.casefold():
                    window.Edit()

    @staticmethod
    def _activate(application, app: str, document: str) -> None:
        collection = {
            "word": "Documents",
            "excel": "Workbooks",
            "powerpoint": "Presentations",
        }[app]
        documents = getattr(application, collection)
        names = [documents(i).Name for i in range(1, documents.Count + 1)]
        match = next((n for n in names if document.casefold() in n.casefold()), None)
        if match is None:
            raise OfficeError(
                f"No open {app} file matches {document!r}; open files: {names}."
            )
        item = documents(match)
        (item.Windows(1) if app == "powerpoint" else item).Activate()

    def _office_read(self, app: str, sheet: str = "", document: str = "") -> dict:
        return {
            "word": self._word_read,
            "excel": self._excel_read,
            "powerpoint": self._ppt_read,
        }[app](self._app(app, document), sheet)

    def _office_go_to(self, app: str, target: str, document: str = "") -> dict:
        application = self._app(app, document)
        if app == "word":
            return self._word_go_to(application, int(target))
        if app == "excel":
            return self._excel_go_to(application, target)
        slide, _, shape = str(target).partition(":")
        return self._ppt_go_to(application, int(slide), shape.strip())

    def _office_save(self, app: str, document: str = "") -> dict:
        document = self._active_document(self._app(app, document), app)
        document.Save()
        return {"saved": document.FullName}

    def _make_quotation(self, **args) -> dict:
        """A new quotation from the template: Excel file and PDF (see quotation.py)."""
        import quotation

        return quotation.make(args)

    def _save_quotation(self, quote_number: str = "") -> dict:
        """The approved draft: saved as Excel and PDF, PDF opened, draft closed."""
        import quotation

        return quotation.save(quote_number)

    def _office_path(self, app: str, document: str = "") -> dict:
        """The open file's path, and whether it is saved (to attach it to an email)."""
        document = self._active_document(self._app(app, document), app)
        return {"path": document.FullName, "saved": bool(document.Saved)}

    @staticmethod
    def _active_document(application, app: str):
        collection = {
            "word": "Documents",
            "excel": "Workbooks",
            "powerpoint": "Presentations",
        }[app]
        if getattr(application, collection).Count == 0:
            raise OfficeError(f"No {app} file is open.")
        return {
            "word": lambda: application.ActiveDocument,
            "excel": lambda: application.ActiveWorkbook,
            "powerpoint": lambda: application.ActivePresentation,
        }[app]()

    # --- Word ---------------------------------------------------------------------

    @staticmethod
    def _word_doc(application):
        if application.Documents.Count == 0:
            raise OfficeError("No Word document is open.")
        with _suppress_com():
            application.ActiveWindow.View.ReadingLayout = False  # leave Read Mode
        return application.ActiveDocument

    def _word_read(self, application, _sheet: str = "") -> dict:
        doc = self._word_doc(application)
        paragraphs = []
        for i in range(1, min(doc.Paragraphs.Count, 400) + 1):
            text = doc.Paragraphs(i).Range.Text.strip()
            if text:
                paragraphs.append({"paragraph": i, "text": _short(text)})
        return {
            "document": doc.Name,
            "paragraphs": paragraphs,
            "total_paragraphs": doc.Paragraphs.Count,
            "track_changes": bool(doc.TrackRevisions),
        }

    def _word_go_to(self, application, paragraph: int) -> dict:
        doc = self._word_doc(application)
        rng = self._word_paragraph(doc, paragraph)
        rng.Select()
        application.ActiveWindow.ScrollIntoView(rng, True)
        return {"showing_paragraph": paragraph, "text": _short(rng.Text)}

    @staticmethod
    def _word_paragraph(doc, paragraph: int):
        if not 1 <= paragraph <= doc.Paragraphs.Count:
            raise OfficeError(
                f"There is no paragraph {paragraph}; the document has {doc.Paragraphs.Count}."
            )
        rng = doc.Paragraphs(paragraph).Range
        rng.MoveEnd(1, -1)  # wdCharacter: leave the paragraph mark alone
        return rng

    def _word_edit(
        self,
        find: str = "",
        replace_with: str = "",
        paragraph: int = 0,
        text: str = "",
        insert_after: bool = False,
        document: str = "",
    ) -> dict:
        application = self._app("word", document)
        doc = self._word_doc(application)
        doc.TrackRevisions = True  # the user sees every change as a tracked change
        if find:
            # The exact text as stored (office_read shows line breaks as spaces)
            actual = _as_stored(doc.Content.Text, find)
            if actual is None:
                raise OfficeError(f"{find!r} is not in the document.")
            count = doc.Content.Text.count(actual)
            # Word's Find writes a paragraph mark as ^p and a line break as ^l
            find = actual.replace(chr(13), "^p").replace(chr(11), "^l")
            if len(find) > 255:
                raise OfficeError(
                    "The text to find is too long; change the whole paragraph instead."
                )
            # Positional: Word ignores Find.Execute's named arguments over COM
            _word_find(doc.Content, find, replace_with, replace_all=True)
            first = doc.Content
            if _word_find(first, replace_with or find):
                first.Select()
                application.ActiveWindow.ScrollIntoView(first, True)
            return {"replaced": count, "tracked": True}
        rng = self._word_paragraph(doc, paragraph)
        if insert_after:
            rng.InsertParagraphAfter()
            rng = self._word_paragraph(doc, paragraph + 1)
        rng.Text = text
        rng.Select()
        application.ActiveWindow.ScrollIntoView(rng, True)
        return {
            "paragraph": paragraph + 1 if insert_after else paragraph,
            "tracked": True,
        }

    # --- Excel --------------------------------------------------------------------

    @staticmethod
    def _excel_sheet(application, sheet: str = ""):
        if application.Workbooks.Count == 0:
            raise OfficeError("No Excel workbook is open.")
        workbook = application.ActiveWorkbook
        if sheet:
            names = [
                workbook.Worksheets(i).Name
                for i in range(1, workbook.Worksheets.Count + 1)
            ]
            match = next((n for n in names if n.casefold() == sheet.casefold()), None)
            if match is None:
                raise OfficeError(f"There is no sheet {sheet!r}; sheets: {names}.")
            workbook.Worksheets(match).Activate()
        return workbook, application.ActiveSheet

    def _excel_read(self, application, sheet: str = "") -> dict:
        workbook, ws = self._excel_sheet(application, sheet)
        used = ws.UsedRange
        rows, cols = min(used.Rows.Count, 60), min(used.Columns.Count, 26)
        block = ws.Range(used.Cells(1, 1), used.Cells(rows, cols))
        values = block.Value
        if not isinstance(values, tuple):
            values = ((values,),)
        return {
            "workbook": workbook.Name,
            "sheets": [
                workbook.Worksheets(i).Name
                for i in range(1, workbook.Worksheets.Count + 1)
            ],
            "sheet": ws.Name,
            "range": _address(block),
            "rows": [[_plain(v) for v in row] for row in values],
            "truncated": used.Rows.Count > rows or used.Columns.Count > cols,
        }

    def _excel_go_to(self, application, target: str) -> dict:
        sheet, _, cell = target.rpartition("!")
        _, ws = self._excel_sheet(application, sheet.strip("'"))
        rng = ws.Range(cell)
        application.Goto(rng, True)  # select it and scroll it into view
        return {"showing": f"{ws.Name}!{_address(rng)}"}

    def _excel_set_cells(
        self, cells: dict, sheet: str = "", document: str = ""
    ) -> dict:
        application = self._app("excel", document)
        _, ws = self._excel_sheet(application, sheet)
        changed = []
        for address, value in cells.items():
            rng = ws.Range(address)
            text = str(value)
            if text.startswith("="):
                rng.Formula = text
            else:
                rng.Value = _number_or_text(text)
            rng.Interior.Color = YELLOW  # highlight the change
            changed.append(_address(rng))
        if changed:
            application.Goto(ws.Range(changed[0]), True)
        return {"sheet": ws.Name, "changed": changed, "highlighted": True}

    # --- PowerPoint ---------------------------------------------------------------

    @staticmethod
    def _presentation(application):
        if application.Presentations.Count == 0:
            raise OfficeError("No PowerPoint presentation is open.")
        with _suppress_com():
            if application.ActiveWindow.ViewType != 9:
                application.ActiveWindow.ViewType = (
                    9  # ppViewNormal: slide + thumbnails
                )
        return application.ActivePresentation

    def _ppt_read(self, application, _sheet: str = "") -> dict:
        pres = self._presentation(application)
        slides = []
        for slide in pres.Slides:
            shapes = []
            for shape in slide.Shapes:
                if shape.HasTextFrame and shape.TextFrame.HasText:
                    shapes.append(
                        {
                            "shape": shape.Name,
                            "text": _short(shape.TextFrame.TextRange.Text),
                        }
                    )
            slides.append({"slide": slide.SlideIndex, "shapes": shapes})
            if len(slides) >= 80:
                break
        current = None
        with _suppress_com():
            current = application.ActiveWindow.View.Slide.SlideIndex
        return {
            "presentation": pres.Name,
            "current_slide": current,
            "total_slides": pres.Slides.Count,
            "slides": slides,
        }

    def _ppt_go_to(self, application, slide: int, shape: str = "") -> dict:
        pres = self._presentation(application)
        if not 1 <= slide <= pres.Slides.Count:
            raise OfficeError(
                f"There is no slide {slide}; the deck has {pres.Slides.Count} slides."
            )
        application.ActiveWindow.View.GotoSlide(slide)
        if shape:
            self._ppt_shape(pres, slide, shape).Select()
        return {"showing_slide": slide, "selected_shape": shape or None}

    @staticmethod
    def _ppt_shape(pres, slide: int, shape: str):
        names = [s.Name for s in pres.Slides(slide).Shapes]
        match = next((n for n in names if n.casefold() == shape.casefold()), None)
        if match is None:
            raise OfficeError(f"Slide {slide} has no shape {shape!r}; shapes: {names}.")
        return pres.Slides(slide).Shapes(match)

    def _ppt_edit(
        self,
        slide: int,
        shape: str = "",
        text: str = "",
        find: str = "",
        replace_with: str = "",
        document: str = "",
    ) -> dict:
        application = self._app("powerpoint", document)
        pres = self._presentation(application)
        if not 1 <= slide <= pres.Slides.Count:
            raise OfficeError(
                f"There is no slide {slide}; the deck has {pres.Slides.Count} slides."
            )
        application.ActiveWindow.View.GotoSlide(slide)
        if find:
            replaced = 0
            for sh in pres.Slides(slide).Shapes:
                if not (sh.HasTextFrame and sh.TextFrame.HasText):
                    continue
                text_range = sh.TextFrame2.TextRange
                # The exact text as stored (office_read shows line breaks as spaces)
                actual = _as_stored(text_range.Text, find)
                if actual is None:
                    continue
                after = 0  # search on after each replacement ("cat" -> "cats" must not loop)
                while (
                    found := text_range.Replace(actual, replace_with, after)
                ) is not None:
                    start = (
                        found.Start
                    )  # found keeps the old length: look the new text up
                    if replace_with:
                        _highlight(text_range.Find(replace_with, start - 1))
                    replaced += 1
                    after = start - 1 + len(replace_with)
            if not replaced:
                raise OfficeError(f"{find!r} is not on slide {slide}.")
            return {"slide": slide, "replaced": replaced, "highlighted": True}
        target = self._ppt_shape(pres, slide, shape)
        target.TextFrame.TextRange.Text = text
        _highlight(target.TextFrame2.TextRange)
        target.Select()
        return {"slide": slide, "shape": target.Name, "highlighted": True}


def _as_stored(stored: str, find: str) -> str | None:
    """The text in a document that matches find, where any run of spaces and line
    breaks matches any other: office_read joins lines with spaces, so a phrase
    copied from it can span a line break that the document stores as \r or \v."""
    words = find.split()
    if not words:
        return None
    match = re.search(r"\s+".join(re.escape(w) for w in words), stored)
    return match.group(0) if match else None


def _word_find(
    rng, text: str, replace_with: str = "", *, replace_all: bool = False
) -> bool:
    # FindText, MatchCase, MatchWholeWord, MatchWildcards, MatchSoundsLike,
    # MatchAllWordForms, Forward, Wrap (0 = stop), Format, ReplaceWith, Replace (2 = all)
    return bool(
        rng.Find.Execute(
            text,
            True,
            False,
            False,
            False,
            False,
            True,
            0,
            False,
            replace_with,
            2 if replace_all else 0,
        )
    )


def _highlight(text_range) -> None:
    """Yellow text highlight on a TextRange2 (PowerPoint 2019+; skipped on older versions)."""
    if text_range is None:
        return
    with _suppress_com():
        text_range.Font.Highlight.RGB = YELLOW


def _address(rng) -> str:
    return rng.Address.replace("$", "")  # "$A$1:$F$20" -> "A1:F20"


def _number_or_text(text: str):
    if re.fullmatch(r"-?\d+(\.\d+)?", text.strip()):
        number = float(text)
        return int(number) if number.is_integer() else number
    return text


def _suppress_com():
    """Ignore COM errors for best-effort steps (view changes, highlighting)."""
    import pywintypes

    return contextlib.suppress(pywintypes.com_error, AttributeError)
