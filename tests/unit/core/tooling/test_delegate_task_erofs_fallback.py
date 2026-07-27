from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for sandbox-resilient delegate_task EROFS fallback.

Sandboxed ``delegate_task`` cannot write another anima's
``task_queue.jsonl`` / ``state/pending/``; the handler must fall back to
``POST /api/internal/delegate-task`` with residual persist flags.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.exceptions import TaskPersistenceError
from core.tooling.handler import ToolHandler


def _make_handler(tmp_path: Path, anima_name: str = "rin") -> ToolHandler:
    anima_dir = tmp_path / "animas" / anima_name
    anima_dir.mkdir(parents=True, exist_ok=True)
    (anima_dir / "permissions.md").write_text("", encoding="utf-8")
    (anima_dir / "state").mkdir(exist_ok=True)
    (anima_dir / "status.json").write_text("{}", encoding="utf-8")

    memory = MagicMock()
    memory.read_permissions.return_value = ""
    messenger = MagicMock()
    msg = MagicMock()
    msg.id = "m1"
    msg.thread_id = "t1"
    messenger.send.return_value = msg

    return ToolHandler(
        anima_dir=anima_dir,
        memory=memory,
        messenger=messenger,
    )


def _setup_target(tmp_path: Path, name: str = "natsume") -> Path:
    target = tmp_path / "animas" / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "state").mkdir(exist_ok=True)
    (target / "status.json").write_text("{}", encoding="utf-8")
    return target


def _delegate_args() -> dict:
    return {
        "name": "natsume",
        "instruction": "resolve PR conflicts",
        "summary": "PR conflicts",
        "deadline": "2h",
    }


class TestDelegateTaskErofsFallback:
    def test_add_task_oserror_falls_back_with_all_persist_flags(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        handler = _make_handler(tmp_path)
        _setup_target(tmp_path)
        monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "http://server.test:18500")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "sub_task_id": "abc",
            "tracking_task_id": "def",
        }

        with (
            patch.object(handler, "_check_subordinate", return_value=None),
            patch("core.paths.get_animas_dir", return_value=tmp_path / "animas"),
            patch(
                "core.memory.task_queue.TaskQueueManager.add_task",
                side_effect=OSError(30, "Read-only file system"),
            ),
            patch("httpx.post", return_value=mock_resp) as mock_post,
            patch(
                "core.tooling.handler_delegation._record_taskboard_delegation"
            ) as mock_tb,
        ):
            result = handler.handle("delegate_task", _delegate_args())

        # Success is a human-readable string (not error JSON)
        assert not result.strip().startswith("{")
        assert "natsume" in result
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        assert url == "http://server.test:18500/api/internal/delegate-task"
        payload = mock_post.call_args[1]["json"]
        assert payload["persist_sub"] is True
        assert payload["persist_tracking"] is True
        assert payload["persist_pending"] is True
        assert payload["delegator"] == "rin"
        assert payload["target"] == "natsume"
        assert payload["instruction"] == "resolve PR conflicts"
        assert len(payload["sub_task_id"]) == 12
        assert len(payload["tracking_task_id"]) == 12
        assert payload["sub_task_id"] in result
        assert payload["tracking_task_id"] in result
        # Server already recorded TaskBoard; local call skipped
        mock_tb.assert_not_called()

    def test_add_task_persistence_error_falls_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TaskQueueManager wraps OSError in TaskPersistenceError (not an
        OSError subclass); the fallback must fire for it too. Regression for
        the 2026-07-22 production incident where EROFS delegations kept
        failing despite the deployed fallback."""
        handler = _make_handler(tmp_path)
        _setup_target(tmp_path)
        monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "http://server.test:18500")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}

        with (
            patch.object(handler, "_check_subordinate", return_value=None),
            patch("core.paths.get_animas_dir", return_value=tmp_path / "animas"),
            patch(
                "core.memory.task_queue.TaskQueueManager.add_task",
                side_effect=TaskPersistenceError(
                    "[Errno 30] Read-only file system: 'task_queue.jsonl'"
                ),
            ),
            patch("httpx.post", return_value=mock_resp) as mock_post,
            patch(
                "core.tooling.handler_delegation._record_taskboard_delegation"
            ) as mock_tb,
        ):
            result = handler.handle("delegate_task", _delegate_args())

        assert not result.strip().startswith("{")
        assert "natsume" in result
        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        assert payload["persist_sub"] is True
        assert payload["persist_tracking"] is True
        assert payload["persist_pending"] is True
        mock_tb.assert_not_called()

    def test_tracking_oserror_skips_already_persisted_sub(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        handler = _make_handler(tmp_path)
        _setup_target(tmp_path)
        monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "http://server.test:18500")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}

        sub_entry = MagicMock()
        sub_entry.task_id = "subid0000001"

        with (
            patch.object(handler, "_check_subordinate", return_value=None),
            patch("core.paths.get_animas_dir", return_value=tmp_path / "animas"),
            patch(
                "core.memory.task_queue.TaskQueueManager.add_task",
                return_value=sub_entry,
            ),
            patch(
                "core.memory.task_queue.TaskQueueManager.add_delegated_task",
                side_effect=OSError(30, "Read-only file system"),
            ),
            patch("httpx.post", return_value=mock_resp) as mock_post,
        ):
            result = handler.handle("delegate_task", _delegate_args())

        assert "natsume" in result
        payload = mock_post.call_args[1]["json"]
        assert payload["persist_sub"] is False
        assert payload["persist_tracking"] is True
        assert payload["persist_pending"] is True

    def test_fallback_http_failure_returns_persistence_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        handler = _make_handler(tmp_path)
        _setup_target(tmp_path)
        monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "http://server.test:18500")

        with (
            patch.object(handler, "_check_subordinate", return_value=None),
            patch("core.paths.get_animas_dir", return_value=tmp_path / "animas"),
            patch(
                "core.memory.task_queue.TaskQueueManager.add_task",
                side_effect=OSError(30, "Read-only file system"),
            ),
            patch(
                "httpx.post",
                side_effect=httpx.ConnectError("connection refused"),
            ),
        ):
            result = handler.handle("delegate_task", _delegate_args())

        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "PersistenceFailed"
        assert "Read-only file system" in parsed["message"]
        assert "connection refused" in parsed["message"].lower() or "unreachable" in parsed["message"].lower()

    def test_fallback_server_500_returns_persistence_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        handler = _make_handler(tmp_path)
        _setup_target(tmp_path)
        monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "http://server.test:18500")

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {"detail": "internal boom"}
        mock_resp.text = "internal boom"

        with (
            patch.object(handler, "_check_subordinate", return_value=None),
            patch("core.paths.get_animas_dir", return_value=tmp_path / "animas"),
            patch(
                "core.memory.task_queue.TaskQueueManager.add_task",
                side_effect=OSError(30, "Read-only file system"),
            ),
            patch("httpx.post", return_value=mock_resp),
        ):
            result = handler.handle("delegate_task", _delegate_args())

        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "PersistenceFailed"
        assert "Read-only file system" in parsed["message"]
        assert "500" in parsed["message"] or "internal boom" in parsed["message"]

    def test_direct_success_skips_httpx(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        handler = _make_handler(tmp_path)
        _setup_target(tmp_path)
        monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "http://server.test:18500")

        with (
            patch.object(handler, "_check_subordinate", return_value=None),
            patch("core.paths.get_animas_dir", return_value=tmp_path / "animas"),
            patch(
                "core.tooling.handler_delegation._record_taskboard_delegation"
            ) as mock_tb,
            patch("httpx.post") as mock_post,
        ):
            result = handler.handle("delegate_task", _delegate_args())

        assert "natsume" in result
        mock_post.assert_not_called()
        mock_tb.assert_called_once()

        sub_queue = tmp_path / "animas" / "natsume" / "state" / "task_queue.jsonl"
        own_queue = tmp_path / "animas" / "rin" / "state" / "task_queue.jsonl"
        assert sub_queue.exists()
        assert own_queue.exists()
        sub_task = json.loads(sub_queue.read_text(encoding="utf-8").strip().split("\n")[-1])
        assert sub_task["status"] == "pending"
        own_task = json.loads(own_queue.read_text(encoding="utf-8").strip().split("\n")[-1])
        assert own_task["status"] == "delegated"
        pending = list((tmp_path / "animas" / "natsume" / "state" / "pending").glob("*.json"))
        assert len(pending) == 1

    def test_read_timeout_retries_then_succeeds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """httpx ReadTimeout on first attempt is retried once and can succeed."""
        handler = _make_handler(tmp_path)
        _setup_target(tmp_path)
        monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "http://server.test:18500")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}

        with (
            patch.object(handler, "_check_subordinate", return_value=None),
            patch("core.paths.get_animas_dir", return_value=tmp_path / "animas"),
            patch(
                "core.memory.task_queue.TaskQueueManager.add_task",
                side_effect=OSError(30, "Read-only file system"),
            ),
            patch(
                "httpx.post",
                side_effect=[httpx.ReadTimeout("timed out"), mock_resp],
            ) as mock_post,
            patch("time.sleep") as mock_sleep,
        ):
            result = handler.handle("delegate_task", _delegate_args())

        assert not result.strip().startswith("{")
        assert "natsume" in result
        assert mock_post.call_count == 2
        mock_sleep.assert_called_once_with(2.0)
        timeout_arg = mock_post.call_args_list[0][1]["timeout"]
        assert isinstance(timeout_arg, httpx.Timeout)
        assert timeout_arg.connect == 5.0
        assert timeout_arg.read == 60.0

    def test_memory_write_error_triggers_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MemoryWriteError from pending atomic write must trigger server fallback."""
        from core.exceptions import MemoryWriteError

        handler = _make_handler(tmp_path)
        _setup_target(tmp_path)
        monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "http://server.test:18500")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}

        sub_entry = MagicMock()
        sub_entry.task_id = "subid0000001"

        with (
            patch.object(handler, "_check_subordinate", return_value=None),
            patch("core.paths.get_animas_dir", return_value=tmp_path / "animas"),
            patch(
                "core.memory.task_queue.TaskQueueManager.add_task",
                return_value=sub_entry,
            ),
            patch(
                "core.memory.task_queue.TaskQueueManager.add_delegated_task",
                return_value=MagicMock(),
            ),
            patch(
                "core.tooling.handler_delegation.atomic_write_text",
                side_effect=MemoryWriteError("Atomic write failed: Read-only file system"),
            ),
            patch("httpx.post", return_value=mock_resp) as mock_post,
            patch(
                "core.tooling.handler_delegation._record_taskboard_delegation"
            ) as mock_tb,
        ):
            result = handler.handle("delegate_task", _delegate_args())

        assert not result.strip().startswith("{")
        assert "natsume" in result
        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        assert payload["persist_sub"] is False
        assert payload["persist_tracking"] is False
        assert payload["persist_pending"] is True
        mock_tb.assert_not_called()

    def test_mcp_env_includes_server_url(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Codex MCP env must inject ANIMAWORKS_SERVER_URL (contract for EROFS fallback)."""
        from core.execution.codex_sdk import CodexSDKExecutor
        from core.schemas import ModelConfig

        anima_dir = tmp_path / "animas" / "rin"
        anima_dir.mkdir(parents=True)
        model = ModelConfig(model="codex/gpt-5.6-sol", api_key="sk-test")
        executor = CodexSDKExecutor(model_config=model, anima_dir=anima_dir)
        monkeypatch.delenv("ANIMAWORKS_SERVER_URL", raising=False)
        env = executor._build_mcp_env()
        assert "ANIMAWORKS_SERVER_URL" in env
        assert env["ANIMAWORKS_SERVER_URL"].startswith("http")
        assert "18500" in env["ANIMAWORKS_SERVER_URL"]
