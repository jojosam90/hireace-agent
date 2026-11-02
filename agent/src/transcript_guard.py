"""Keep on-screen transcripts in the conversation's language.

Speech recognition treats the configured language only as a hint: with
an accent it sometimes writes English words phonetically in another script
("계 오픈 샌드박스 폼" for "open sandbox"). The model still understands the audio,
but the text shown to the user is unreadable. These helpers decide what may be
displayed; both the web and the mobile app receive the cleaned text.
"""

from __future__ import annotations

import re
import unicodedata

# Notice shown instead of a transcript that came out in the wrong script
UNCLEAR = {
    "en": "(Sorry, I didn't catch that clearly)",
    "zh": "（抱歉，没有听清楚）",
}


def _allowed(char: str, language: str) -> bool:
    """Whether a letter belongs to a script that may appear in this language."""
    name = unicodedata.name(char, "")
    if name.startswith("LATIN") or char.isascii():
        return True  # English words (and URLs, names) are fine in both languages
    if language == "zh":
        return name.startswith(("CJK", "IDEOGRAPHIC", "FULLWIDTH", "HALFWIDTH"))
    return False


def _is_letter(char: str) -> bool:
    return unicodedata.category(char).startswith("L")


def has_foreign_script(text: str, language: str) -> bool:
    return any(_is_letter(c) and not _allowed(c, language) for c in text)


def clean_user_transcript(text: str, language: str) -> str:
    """The user's words as displayed: tidied, or a notice if unreadable."""
    if has_foreign_script(text, language):
        return UNCLEAR.get(language, UNCLEAR["en"])
    if not text.strip():
        return text
    text = drop_fillers(text)
    if not text:  # nothing but "um"s
        return UNCLEAR.get(language, UNCLEAR["en"])
    if language == "zh":
        return tidy_chinese(text)
    return text[:1].upper() + text[1:]


# --- Mumbling ----------------------------------------------------------------------
# Used when the rephrasing model is unavailable: at least drop the "um"s and stutters.

_FILLER_EN = re.compile(r"\b(?:u+m+|u+h+|e+r+m*|h+m+|a+h+|e+h+|mm+)\b[,.]?\s*", re.IGNORECASE)
_FILLER_ZH = re.compile("[嗯呃唔]+[，,。.]?")
_REPEATED_WORD = re.compile(r"\b(\w+)(?:[,\s]+\1\b)+", re.IGNORECASE)


def drop_fillers(text: str) -> str:
    text = _FILLER_ZH.sub("", _FILLER_EN.sub("", text))
    text = _REPEATED_WORD.sub(r"\1", text)  # "the the" -> "the"
    return _MULTI_SPACE_ANY.sub(" ", text).strip(" ,")


_MULTI_SPACE_ANY = re.compile(r"\s{2,}")


# --- Chinese readability ---------------------------------------------------------
# Speech transcripts of Chinese put spaces between words ("随时 准备") and often
# use English punctuation ("您好, 先生"). Spaces next to English words are kept.

_CJK = "　-〿㐀-䶿一-鿿＀-￯"
_CJK_GAP = re.compile(f"(?<=[{_CJK}])\\s+(?=[{_CJK}])")
_ASCII_PUNCT_AFTER_CJK = re.compile("(?<=[㐀-䶿一-鿿])\\s*([,?!:;])\\s*")
_FULL_WIDTH = {",": "，", "?": "？", "!": "！", ":": "：", ";": "；"}


def _is_cjk(char: str) -> bool:
    return bool(char) and bool(re.match(f"[{_CJK}]", char))


def tidy_chinese(text: str) -> str:
    text = _ASCII_PUNCT_AFTER_CJK.sub(lambda m: _FULL_WIDTH[m.group(1)], text)
    return _CJK_GAP.sub("", text)


class ChunkCleaner:
    """Cleans the agent's streamed text chunk by chunk, including across chunk edges."""

    def __init__(self, language: str) -> None:
        self._language = language
        self._last = ""  # last character emitted
        self._pending_space = ""  # whitespace held back until the next chunk

    def clean(self, chunk: str) -> str:
        chunk = clean_agent_text(chunk, self._language)
        if self._language != "zh" or not chunk:
            return chunk
        text = self._pending_space + chunk
        self._pending_space = ""
        # Decide on whitespace that touches the previous chunk
        stripped = text.lstrip()
        if stripped != text and _is_cjk(self._last) and _is_cjk(stripped[:1]):
            text = stripped
        # English punctuation right after a Chinese character from the last chunk
        if text[:1] in _FULL_WIDTH and re.match("[㐀-䶿一-鿿]", self._last or " "):
            text = _FULL_WIDTH[text[0]] + text[1:].lstrip()
        text = tidy_chinese(text)
        # Hold trailing whitespace: the next chunk decides whether it stays
        body = text.rstrip()
        self._pending_space = text[len(body) :]
        if body:
            self._last = body[-1]
        return body


_SPACES_BEFORE_PUNCT = re.compile(r"\s+([,.!?;:，。？！；：])")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def clean_agent_text(text: str, language: str) -> str:
    """The agent's words as displayed: stray foreign-script fragments removed."""
    if not has_foreign_script(text, language):
        return text
    kept = "".join(c for c in text if not (_is_letter(c) and not _allowed(c, language)))
    kept = _SPACES_BEFORE_PUNCT.sub(r"\1", kept)
    return _MULTI_SPACE.sub(" ", kept)
