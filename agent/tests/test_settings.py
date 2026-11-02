import json
import os

import pytest

from settings import FIELDS, Settings


@pytest.fixture
def settings(tmp_path, monkeypatch):
    # Every variable a setting writes goes back to how it was after the test
    for env in FIELDS.values():
        monkeypatch.setenv(env, "")
        monkeypatch.delenv(env)
    monkeypatch.setenv("OPENAI_VOICE", "ash")  # the .env.local default
    monkeypatch.setenv("OPENAI_API_KEY", "sk-default000000000000000000")
    return Settings(tmp_path / "settings.json")


def test_a_saved_setting_takes_effect_and_clearing_it_restores_the_default(settings):
    assert settings.save({"voice": "cedar"}) == {}
    assert os.environ["OPENAI_VOICE"] == "cedar"
    assert settings.public()["values"]["voice"] == "cedar"

    assert settings.save({"voice": ""}) == {}
    assert os.environ["OPENAI_VOICE"] == "ash"


def test_a_new_process_applies_what_was_saved(settings, tmp_path, monkeypatch):
    settings.save({"voice": "verse"})
    monkeypatch.setenv("OPENAI_VOICE", "ash")  # e.g. the agent, just started

    Settings(tmp_path / "settings.json").apply()

    assert os.environ["OPENAI_VOICE"] == "verse"


def test_the_api_key_is_never_shown_and_kept_when_left_empty(settings, tmp_path):
    key = "sk-proj-abcdefghijklmnopqrstuvwxyz1234"
    assert settings.save({"openai_api_key": key}) == {}
    assert settings.public()["values"]["openai_api_key"] == "…1234"

    assert settings.save({"openai_api_key": "", "voice": "echo"}) == {}
    assert os.environ["OPENAI_API_KEY"] == key
    assert json.loads((tmp_path / "settings.json").read_text())["openai_api_key"] == key


def test_wrong_values_are_reported_and_nothing_is_saved(settings, tmp_path):
    errors = settings.save(
        {
            "voice": "robot",
            "openai_api_key": "hello",
            "quote_dir": str(tmp_path / "missing"),
            "price_list": str(tmp_path),
            "search_dirs": f"{tmp_path};{tmp_path / 'nope'}",
            "colour": "blue",
        }
    )
    assert set(errors) == {
        "voice",
        "openai_api_key",
        "quote_dir",
        "price_list",
        "search_dirs",
        "colour",
    }
    assert "nope" in errors["search_dirs"]
    assert not (tmp_path / "settings.json").exists()
    assert os.environ["OPENAI_VOICE"] == "ash"


def test_files_and_folders_that_exist_are_accepted(settings, tmp_path):
    template = tmp_path / "Quotation.xlsx"
    template.write_bytes(b"x")
    assert (
        settings.save({"quote_template": str(template), "quote_dir": str(tmp_path)})
        == {}
    )
    assert os.environ["QUOTE_TEMPLATE"] == str(template)
    assert settings.save({"quote_template": str(tmp_path / "x.docx")}) == {
        "quote_template": "No such file."
    }
