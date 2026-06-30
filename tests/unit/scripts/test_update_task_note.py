from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "update_task_note.py"
    spec = importlib.util.spec_from_file_location("update_task_note", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()

CLEAN_NOTE = (
    "---\n"
    "カテゴリ: 文芸\n"
    "タスクコード: LIT-014\n"
    "タスク名: 短編小説の初稿\n"
    "ステータス: 進行中\n"
    "daily_ops_copy_id: abc-123\n"
    "次アクション期限: 2026-06-20\n"
    "今週タスク: 構成を練る\n"
    "---\n"
    "\n"
    "# 短編小説の初稿\n"
    "\n"
    "本文は日本語で書かれている。改行も保持されること。\n"
)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "LIT-014.md"
    path.write_bytes(text.encode("utf-8"))
    return path


def test_roundtrip_updates_fields_without_mojibake(tmp_path: Path) -> None:
    path = _write(tmp_path, CLEAN_NOTE)

    res = SCRIPT.update_task_note(path, {"次アクション期限": "2026-07-10", "今週タスク": "初稿を仕上げる"})

    assert res["ok"] is True
    assert res["checks"] == {"values_written": True, "no_mojibake": True}

    reread = path.read_bytes().decode("utf-8")
    # Untouched JP frontmatter survives intact (the corruption signature).
    assert "カテゴリ: 文芸" in reread
    assert "繧ｫ" not in reread and "繝" not in reread
    # Updated values landed.
    assert "次アクション期限: 2026-07-10" in reread
    assert "今週タスク: 初稿を仕上げる" in reread
    # Old values gone, no duplicate keys.
    assert "2026-06-20" not in reread
    assert reread.count("今週タスク:") == 1
    # Body preserved exactly.
    assert "本文は日本語で書かれている。改行も保持されること。" in reread


def test_write_is_utf8_lf_no_bom(tmp_path: Path) -> None:
    path = _write(tmp_path, CLEAN_NOTE)
    SCRIPT.update_task_note(path, {"今週タスク": "推敲"})

    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")  # no BOM
    assert b"\r\n" not in raw  # LF only
    assert "文芸".encode() in raw  # genuine UTF-8 bytes
    raw.decode("utf-8")  # valid UTF-8 throughout


def test_replacing_list_value_consumes_continuation_lines(tmp_path: Path) -> None:
    note = (
        "---\n"
        "カテゴリ: 文芸\n"
        "今週タスク:\n"
        "  - 構成を練る\n"
        "  - 初稿を書く\n"
        "次アクション期限: 2026-06-20\n"
        "---\n"
        "\n"
        "本文。\n"
    )
    path = _write(tmp_path, note)
    res = SCRIPT.update_task_note(path, {"今週タスク": "初稿を仕上げる"})

    assert res["ok"] is True
    reread = path.read_bytes().decode("utf-8")
    # The old list items must be gone, not orphaned under the new scalar.
    assert "  - 構成を練る" not in reread
    assert "  - 初稿を書く" not in reread
    assert "今週タスク: 初稿を仕上げる" in reread
    # Sibling keys (before and after the list) survive intact.
    assert "カテゴリ: 文芸" in reread
    assert "次アクション期限: 2026-06-20" in reread
    # Result is still parseable: every frontmatter line is a top-level key.
    _, fm, _ = SCRIPT._split_frontmatter(reread)
    assert all(line.strip() == "" or SCRIPT._parse_key(line) is not None for line in fm)


def test_missing_key_is_appended_inside_frontmatter(tmp_path: Path) -> None:
    path = _write(tmp_path, CLEAN_NOTE)
    res = SCRIPT.update_task_note(path, {"レビュー担当": "さくら"})

    assert res["ok"] is True
    assert res["added"] == ["レビュー担当"]
    reread = path.read_bytes().decode("utf-8")
    head = reread.split("---\n", 2)
    # The new key lives inside the frontmatter block, before the body fence.
    assert "レビュー担当: さくら" in head[1]


def test_refuses_already_corrupt_note(tmp_path: Path) -> None:
    corrupt = CLEAN_NOTE.replace("カテゴリ: 文芸", "繧ｫ繝・ざ繝ｪ: 譁・敢")
    path = _write(tmp_path, corrupt)
    before = path.read_bytes()

    res = SCRIPT.update_task_note(path, {"今週タスク": "推敲"})

    assert res["ok"] is False
    assert res.get("corrupt") is True
    # The note must not have been rewritten.
    assert path.read_bytes() == before


def test_refuses_mojibaked_update_value(tmp_path: Path) -> None:
    path = _write(tmp_path, CLEAN_NOTE)
    res = SCRIPT.update_task_note(path, {"今週タスク": "繝ｬ繝薙Η繝ｼ蠕・■"})
    assert res["ok"] is False
    assert "mojibak" in str(res.get("error", "")).lower()


def test_value_with_colon_roundtrips_via_quoting(tmp_path: Path) -> None:
    path = _write(tmp_path, CLEAN_NOTE)
    value = "10:00 開始: 会議室A"
    SCRIPT.update_task_note(path, {"今週タスク": value})

    reread = path.read_bytes().decode("utf-8")
    _, fm, _ = SCRIPT._split_frontmatter(reread)
    props = dict(SCRIPT._parse_kv(line) for line in fm)
    assert props["今週タスク"] == value


def test_cli_exit_code_and_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path, CLEAN_NOTE)
    code = SCRIPT.main(["--note", str(path), "--set", "次アクション期限=2026-08-01"])
    assert code == 0
    out = capsys.readouterr().out
    assert '"ok": true' in out
    assert "2026-08-01" in path.read_bytes().decode("utf-8")
