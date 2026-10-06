from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Startup diagnostics for optional execution SDKs and their CLIs."""

import json
import logging
import os
from pathlib import Path

from core.config.model_mode import CLAUDE_CLI_ALIASES

logger = logging.getLogger("animaworks")


def _is_mode_c_status(data: dict) -> bool:
    """Return True when status.json indicates Mode C / codex execution."""
    mode = str(data.get("execution_mode") or data.get("resolved_mode") or "").strip().upper()
    if mode == "C":
        return True
    return str(data.get("model") or "").strip().startswith("codex/")


def _is_mode_s_status(data: dict) -> bool:
    """Return True when status.json indicates Mode S / Claude Agent SDK."""
    mode = str(data.get("execution_mode") or data.get("resolved_mode") or "").strip().upper()
    if mode == "S":
        return True
    model = str(data.get("model") or "").strip().lower()
    return model.startswith(("claude-", "anthropic/")) or model in CLAUDE_CLI_ALIASES


def _package_importable(module_name: str) -> bool:
    """Return True when *module_name* can be imported."""
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def _scan_sdk_dependent_animas(animas_dir: Path) -> tuple[list[str], list[str]]:
    """Return names of animas configured for Mode C and Mode S."""
    mode_c: list[str] = []
    mode_s: list[str] = []
    if not animas_dir.is_dir():
        return mode_c, mode_s

    for anima_dir in sorted(animas_dir.iterdir()):
        if not anima_dir.is_dir():
            continue
        status_path = anima_dir / "status.json"
        if not status_path.is_file():
            continue
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        if _is_mode_c_status(data):
            mode_c.append(anima_dir.name)
        if _is_mode_s_status(data):
            mode_s.append(anima_dir.name)
    return mode_c, mode_s


def run_execution_sdk_preflight(animas_dir: Path | None = None) -> None:
    """Log critical diagnostics when configured SDKs or executables are absent.

    Startup continues so operators can restore the missing dependencies.
    """
    try:
        if animas_dir is None:
            from core.paths import get_animas_dir

            animas_dir = get_animas_dir()

        mode_c, mode_s = _scan_sdk_dependent_animas(animas_dir)

        if mode_c and not _package_importable("openai_codex"):
            names = ", ".join(mode_c)
            logger.critical(
                "Mode C anima %s が存在するが openai-codex パッケージが見つからない。"
                "`uv sync --frozen --all-extras` または "
                "`uv pip install openai-codex openai-codex-cli-bin` で復元せよ。"
                "新規spawnされるプロセスは全て失敗する",
                names,
            )

        if mode_s and not _package_importable("claude_agent_sdk"):
            names = ", ".join(mode_s)
            logger.critical(
                "Mode S anima %s が存在するが claude_agent_sdk パッケージが見つからない。"
                "`uv sync --frozen --all-extras` または "
                "`uv pip install 'animaworks[claude]'` で復元せよ。"
                "新規spawnされるプロセスは全て失敗する",
                names,
            )

        if mode_s:
            names = ", ".join(mode_s)
            try:
                from core.platform.claude_code import get_claude_executable

                cli_path = get_claude_executable()
            except Exception:
                cli_path = None
            if cli_path is None:
                logger.critical(
                    "Mode S anima %s が存在するが Claude Code CLI が見つからない。"
                    "Python SDK は CLI を同梱しない。`npm install -g @anthropic-ai/claude-code` で入れよ。"
                    "CLI が無いと全セッションが『ストリームが3回切断』で失敗する",
                    names,
                )
            if hasattr(os, "geteuid") and os.geteuid() == 0 and os.environ.get("IS_SANDBOX") != "1":
                logger.critical(
                    "root で実行中だが IS_SANDBOX が未設定。"
                    "Claude Code CLI は root で bypassPermissions を拒否して即終了するため、"
                    "Mode S anima %s の全セッションが『ストリームが3回切断』で失敗する。"
                    "隔離コンテナなら `IS_SANDBOX=1` を設定、そうでなければ非 root で起動せよ",
                    names,
                )
    except Exception:
        logger.exception("Execution SDK preflight failed unexpectedly; continuing server startup")
