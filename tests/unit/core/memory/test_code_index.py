from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from core.memory.code_index import search_code


@pytest.fixture
def indexed_project(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    anima_dir = tmp_path / "anima"
    anima_dir.mkdir()
    (anima_dir / "projects.json").write_text(
        json.dumps({"demo": {"repo": str(repo)}}),
        encoding="utf-8",
    )
    return anima_dir, repo


def _track(repo: Path, *paths: str) -> None:
    subprocess.run(["git", "add", "--", *paths], cwd=repo, check=True)


def test_search_code_finds_function_and_reports_lines(indexed_project: tuple[Path, Path]) -> None:
    anima_dir, repo = indexed_project
    (repo / "sample.py").write_text("def LibrarianNeedle():\n    return 42\n", encoding="utf-8")
    _track(repo, "sample.py")

    results = search_code(anima_dir, "demo", "LibrarianNeedle")

    assert isinstance(results, list)
    assert results[0]["source_file"] == "code:demo/sample.py#L1-L2"
    assert results[0]["last_scan"]


def test_search_code_incrementally_replaces_changed_file(
    indexed_project: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir, repo = indexed_project
    source = repo / "sample.py"
    source.write_text("def OldNeedle():\n    pass\n", encoding="utf-8")
    _track(repo, "sample.py")
    assert search_code(anima_dir, "demo", "OldNeedle")

    source.write_text("def ReplacementNeedle():\n    return 'new'\n", encoding="utf-8")
    monkeypatch.setattr("core.memory.code_index._SCAN_DEBOUNCE_SECONDS", 0)

    assert search_code(anima_dir, "demo", "OldNeedle") == []
    updated = search_code(anima_dir, "demo", "ReplacementNeedle")
    assert isinstance(updated, list) and "ReplacementNeedle" in updated[0]["content"]


def test_search_code_excludes_binary_and_files_over_1mb(indexed_project: tuple[Path, Path]) -> None:
    anima_dir, repo = indexed_project
    (repo / "binary.dat").write_bytes(b"BinaryNeedle\0payload")
    (repo / "large.txt").write_bytes(b"LargeNeedle\n" + b"x" * (1024 * 1024))
    _track(repo, "binary.dat", "large.txt")

    assert search_code(anima_dir, "demo", "BinaryNeedle") == []
    assert search_code(anima_dir, "demo", "LargeNeedle") == []
    payload = json.loads((anima_dir / "state" / "code_bm25_demo.json").read_text(encoding="utf-8"))
    assert payload["files"] == {}


def test_search_code_returns_clear_error_for_unknown_project(tmp_path: Path) -> None:
    (tmp_path / "projects.json").write_text("{}", encoding="utf-8")

    result = search_code(tmp_path, "missing", "anything")

    assert isinstance(result, str)
    assert "missing" in result and "not registered" in result
