# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the native ``animaworks demo`` command (cli/demo.py)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from cli import demo


def _make_args(data_dir: Path, **overrides) -> argparse.Namespace:
    defaults = dict(
        preset="en-business",
        data_dir=str(data_dir),
        port=18501,
        host="0.0.0.0",
        reset=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _run_with(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
    *,
    claude_available: bool = True,
    codex_available: bool = False,
    **overrides,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(demo, "_claude_code_available", lambda: claude_available)
    monkeypatch.setattr(demo, "_codex_login_available", lambda: codex_available)
    # Disable actual server startup during tests
    monkeypatch.setattr(demo, "_start_server", lambda args: None)
    demo.cmd_demo(_make_args(data_dir, **overrides))


def test_claude_code_login_init(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    _run_with(monkeypatch, data_dir, claude_available=True, codex_available=False)

    # Claude Code subscription auth is injected into config.json
    cfg = json.loads((data_dir / "config.json").read_text(encoding="utf-8"))
    assert cfg["credentials"]["anthropic"]["type"] == "claude_code_login"
    assert cfg["anima_defaults"]["mode_s_auth"] == "max"

    # All 3 preset characters are created
    anima_names = {p.name for p in (data_dir / "animas").iterdir() if p.is_dir()}
    assert {"alex", "nova", "kai"} <= anima_names

    # local_trust auth.json is generated
    auth = json.loads((data_dir / "auth.json").read_text(encoding="utf-8"))
    assert auth["auth_mode"] == "local_trust"

    # Model override applied (engineer -> sonnet main, general -> haiku)
    kai_status = json.loads((data_dir / "animas" / "kai" / "status.json").read_text(encoding="utf-8"))
    assert kai_status["model"] == "claude-sonnet-4-6"
    nova_status = json.loads((data_dir / "animas" / "nova" / "status.json").read_text(encoding="utf-8"))
    assert nova_status["model"] == "claude-haiku-4-5-20251001"


def test_codex_login_init(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    _run_with(monkeypatch, data_dir, claude_available=False, codex_available=True)

    cfg = json.loads((data_dir / "config.json").read_text(encoding="utf-8"))
    assert cfg["credentials"]["openai"]["type"] == "codex_login"

    # Models get the codex/ prefix
    kai_status = json.loads((data_dir / "animas" / "kai" / "status.json").read_text(encoding="utf-8"))
    assert kai_status["model"] == "codex/gpt-5.4"
    nova_status = json.loads((data_dir / "animas" / "nova" / "status.json").read_text(encoding="utf-8"))
    assert nova_status["model"] == "codex/gpt-5.4-mini"


def test_no_auth_exits_with_code_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(demo, "_claude_code_available", lambda: False)
    monkeypatch.setattr(demo, "_codex_login_available", lambda: False)
    monkeypatch.setattr(demo, "_start_server", lambda args: None)

    with pytest.raises(SystemExit) as exc:
        demo.cmd_demo(_make_args(tmp_path / "data"))
    assert exc.value.code == 1
