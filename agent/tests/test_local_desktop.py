import os
import time

import pytest

from local_desktop import DesktopError, find_files


def _touch(path, *, age_days: float = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))


@pytest.fixture
def tree(tmp_path):
    _touch(tmp_path / "Documents" / "Acme Proposal v1.docx", age_days=10)
    _touch(tmp_path / "Documents" / "clients" / "Acme proposal v2.docx", age_days=1)
    _touch(tmp_path / "Documents" / "Acme proposal budget.xlsx", age_days=2)
    _touch(tmp_path / "Downloads" / "unrelated.pdf")
    _touch(tmp_path / "Documents" / "~$Acme Proposal v1.docx")  # Office lock file
    _touch(tmp_path / "code" / "node_modules" / "acme-proposal.docx")
    (tmp_path / "Pictures" / "Acme Proposal assets").mkdir(parents=True)
    return tmp_path


def _names(result: dict) -> list[str]:
    return [m["name"] for m in result["matches"]]


def test_finds_files_containing_every_word_newest_first(tree):
    result = find_files("acme proposal", [tree])

    assert _names(result) == [
        "Acme proposal v2.docx",
        "Acme proposal budget.xlsx",
        "Acme Proposal v1.docx",
    ]
    assert result["searched_everywhere"] is True
    assert result["matches"][0]["folder"] == str(tree / "Documents" / "clients")


def test_documents_rank_above_newer_code_files(tree):
    _touch(tree / "code" / "ProposalStatus.tsx")  # newest of all
    assert _names(find_files("proposal", [tree]))[-1] == "ProposalStatus.tsx"


def test_kind_filters_by_file_type(tree):
    assert _names(find_files("acme proposal", [tree], kind="excel")) == [
        "Acme proposal budget.xlsx"
    ]


def test_folders_only_when_asked(tree):
    assert _names(find_files("acme proposal", [tree], kind="folder")) == [
        "Acme Proposal assets"
    ]


def test_skips_lock_files_and_code_folders(tree):
    paths = [m["path"] for m in find_files("acme", [tree])["matches"]]
    assert not any("~$" in p or "node_modules" in p for p in paths)


def test_limit_and_total(tree):
    result = find_files("acme", [tree], limit=1)
    assert len(result["matches"]) == 1
    assert result["total_found"] == 3


def test_empty_query_and_unknown_kind_are_errors(tree):
    with pytest.raises(DesktopError):
        find_files("  ", [tree])
    with pytest.raises(DesktopError):
        find_files("acme", [tree], kind="video")


def test_out_of_time_reports_an_incomplete_search(tree):
    result = find_files("acme", [tree], time_budget=-1)
    assert result["searched_everywhere"] is False
