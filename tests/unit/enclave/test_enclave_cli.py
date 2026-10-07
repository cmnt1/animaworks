# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for enclave operational CLI commands."""

from __future__ import annotations

import grp
import json
import os
import socket
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cli.commands import enclave_cmd
from core.config import invalidate_cache
from tests.helpers.filesystem import DEFAULT_TEST_CONFIG


def _write_config(data_dir: Path, socket_path: Path, *, socket_group: str = "test-group") -> None:
    config: dict[str, Any] = dict(DEFAULT_TEST_CONFIG)
    config["enclave"] = {
        "enabled": True,
        "name": "isolated",
        "socket_path": str(socket_path),
        "socket_group": socket_group,
        "entry_anima": "entry-anima",
        "allowed_peer_uids": [os.getuid()],
        "allowed_llm_credentials": ["anthropic"],
        "egress": {"stages": [{"type": "known_values", "sources": []}]},
    }
    (data_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")
    invalidate_cache()


def test_doctor_fails_when_guard_violation_exists(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    socket_path = data_dir / "run" / "enclave.sock"
    _write_config(data_dir, socket_path)
    monkeypatch.setattr("core.enclave.guards.collect_enclave_violations", lambda *args, **kwargs: ["guard violation"])
    monkeypatch.setattr("core.enclave.ops.check_gateway_health", lambda *args, **kwargs: False)
    monkeypatch.setattr(enclave_cmd, "_masker_dependencies", lambda: [])

    with pytest.raises(SystemExit) as exc_info:
        enclave_cmd.enclave_doctor_command(SimpleNamespace(json_output=True))

    assert exc_info.value.code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is False
    assert any(check["status"] == "fail" and check["detail"] == "guard violation" for check in output["checks"])


def test_doctor_passes_when_checks_are_healthy(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Short path: AF_UNIX paths are limited to ~108 bytes, so avoid tmp_path.
    socket_dir = Path(tempfile.mkdtemp(prefix="aw-enc-", dir="/tmp"))
    socket_path = socket_dir / "s.sock"
    server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server_socket.bind(str(socket_path))
        os.chmod(socket_path, 0o660)
        server_socket.close()
        socket_group = grp.getgrgid(os.getegid()).gr_name
        _write_config(data_dir, socket_path, socket_group=socket_group)
        monkeypatch.setattr("core.enclave.guards.collect_enclave_violations", lambda *args, **kwargs: [])
        monkeypatch.setattr("core.enclave.ops.check_gateway_health", lambda *args, **kwargs: True)
        monkeypatch.setattr(enclave_cmd, "_masker_dependencies", lambda: [])

        enclave_cmd.enclave_doctor_command(SimpleNamespace(json_output=False))

        output = capsys.readouterr().out
        assert "guards" in output
        assert "egress_pipeline" in output
        assert "gateway_health" in output
        assert "RESULT" in output
        assert "fail" not in output
    finally:
        server_socket.close()
        socket_path.unlink(missing_ok=True)
        socket_dir.rmdir()


def test_status_prints_counts_without_audit_body(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    today = datetime.now(UTC).strftime("%Y%m%d")
    audit_dir = data_dir / "enclave" / "audit" / "egress"
    audit_dir.mkdir(parents=True)
    (audit_dir / f"{today}.jsonl").write_text(
        json.dumps({"blocked": False, "input_facts": [{"fact": "do-not-print-this"}]})
        + "\n"
        + json.dumps({"blocked": True, "input_facts": [{"fact": "also-secret"}]})
        + "\n",
        encoding="utf-8",
    )

    enclave_cmd.enclave_status_command(SimpleNamespace())

    output = capsys.readouterr().out
    assert output.strip() == "ok=1 blocked=1"
    assert "do-not-print-this" not in output
    assert "also-secret" not in output


def test_parser_registers_doctor_json_option() -> None:
    from cli.parser import build_parser

    args = build_parser().parse_args(["enclave", "doctor", "--json"])

    assert args.enclave_command == "doctor"
    assert args.json_output is True
    assert args.func is enclave_cmd.enclave_doctor_command
