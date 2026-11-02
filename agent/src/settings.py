"""The user's settings, edited in the app (the gear icon) and kept on this PC.

Stored in <data folder>/settings.json. Each setting stands in for an environment
variable (its .env.local value is the default), so the rest of the code keeps
reading os.environ: apply() copies the saved values in. The gatekeeper applies them
when they are saved, the agent at the start of each call.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

# Setting -> the environment variable it sets
FIELDS = {
    "voice": "OPENAI_VOICE",
    "openai_api_key": "OPENAI_API_KEY",
    "email_signature": "EMAIL_SIGNATURE",
    "quote_signature": "QUOTE_SIGNATURE",
    "quote_template": "QUOTE_TEMPLATE",
    "quote_dir": "QUOTE_DIR",
    "quote_pdf_dir": "QUOTE_PDF_DIR",
    "price_list": "QUOTE_PRICE_LIST",
    "search_dirs": "HIREACE_SEARCH_DIRS",
}
# Never sent back to the app in full: it shows only the last four characters
SECRETS = {"openai_api_key"}
# OpenAI Realtime voices; the first is the default (agent.py)
VOICES = (
    # Female
    "marin",
    "coral",
    "sage",
    "shimmer",
    # Neutral
    "alloy",
    # Male
    "ash",
    "ballad",
    "cedar",
    "echo",
    "verse",
)
_FILES = {"quote_template": (".xlsx",), "price_list": (".json",)}
_FOLDERS = {"quote_dir", "quote_pdf_dir"}


def data_dir() -> Path:
    """HireAce's own folder: Chrome profile, audit log, settings. Gmail stays signed in in the Chrome profile."""
    return Path(os.environ.get("HIREACE_DATA_DIR", Path.home() / ".hireace-agent"))


class Settings:
    def __init__(self, path: Path) -> None:
        self._path = path
        # The environment as it was before any setting was applied: clearing a
        # setting goes back to it
        self._defaults = {env: os.environ.get(env) for env in FIELDS.values()}

    def load(self) -> dict[str, str]:
        try:
            saved = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {k: str(v) for k, v in saved.items() if k in FIELDS and v}

    def apply(self) -> None:
        saved = self.load()
        for field, env in FIELDS.items():
            value = saved.get(field) or self._defaults[env]
            if value:
                os.environ[env] = value
            else:
                os.environ.pop(env, None)

    def public(self) -> dict:
        """For the Settings page: every value in effect, secrets masked."""
        saved = self.load()
        values = {}
        for field, env in FIELDS.items():
            value = saved.get(field) or self._defaults[env] or ""
            values[field] = _mask(value) if field in SECRETS else value
        # The agent's own default (agent.py) when none is set
        values["voice"] = values["voice"] or VOICES[0]
        return {"values": values, "voices": list(VOICES)}

    def save(self, changes: dict) -> dict[str, str]:
        """Checks and stores the changed values; returns the problems by field
        (then nothing is stored). An empty value goes back to the default, and a
        secret left empty is kept as it is."""
        errors = {}
        saved = self.load()
        for field, raw in changes.items():
            if field not in FIELDS:
                errors[field] = "Unknown setting."
                continue
            value = str(raw or "").strip()
            if field in SECRETS and not value:
                continue
            if problem := _check(field, value):
                errors[field] = problem
            elif value:
                saved[field] = value
            else:
                saved.pop(field, None)
        if errors:
            return errors
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(saved, indent=2), encoding="utf-8")
        self.apply()
        return {}


def _check(field: str, value: str) -> str:
    if not value:
        return ""
    if field == "voice" and value not in VOICES:
        return "Choose one of the listed voices."
    if field == "openai_api_key" and not re.fullmatch(r"sk-[A-Za-z0-9_\-]{20,}", value):
        return "An OpenAI API key starts with sk-."
    if field in _FILES:
        path = Path(value)
        if not path.is_file():
            return "No such file."
        if path.suffix.lower() not in _FILES[field]:
            return f"Must be a {' or '.join(_FILES[field])} file."
    if field in _FOLDERS and not Path(value).is_dir():
        return "No such folder."
    if field == "search_dirs":
        missing = [
            d for d in value.split(";") if d.strip() and not Path(d.strip()).is_dir()
        ]
        if missing:
            return f"No such folder: {missing[0].strip()}"
    if field in ("email_signature", "quote_signature") and len(value) > 200:
        return "Keep it under 200 characters."
    return ""


def _mask(secret: str) -> str:
    return f"…{secret[-4:]}" if secret else ""
