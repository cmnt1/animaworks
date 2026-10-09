# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for enclave SSM port-forward tunnel management."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from core.config import invalidate_cache
from core.enclave import ssm_tunnel
from core.enclave.config import EnclaveSsmTunnelConfig
from tests.helpers.filesystem import DEFAULT_TEST_CONFIG

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeProc:
    def __init__(self, args: list[str], *, alive: bool = True) -> None:
        self.args = args
        self.alive = alive
        self.terminated = False
        self.killed = False
        self.pid = 4242

    def poll(self) -> int | None:
        return None if self.alive else 0

    def terminate(self) -> None:
        self.terminated = True
        self.alive = False

    def kill(self) -> None:
        self.killed = True
        self.alive = False

    def wait(self, timeout: float | None = None) -> int:  # noqa: ARG002
        return 0


class _FakeSSM:
    def __init__(self, instances: list | None = None, *, multiple: bool = False) -> None:
        self.started: list[dict] = []
        self.describes: list[dict] = []
        self._instances = instances if instances is not None else [{"InstanceId": "i-bastion"}]
        self._multiple = multiple

    def describe_instances(self, **kwargs: Any) -> dict:
        self.describes.append(kwargs)
        instances = self._instances
        if self._multiple:
            instances = instances + [{"InstanceId": "i-other"}]
        return {"Reservations": [{"Instances": instances}]}

    def terminate_session(self, **kwargs: Any) -> dict:
        self.terminated = kwargs
        return {}

    def start_session(self, **kwargs: Any) -> dict:
        self.started.append(kwargs)
        return {"SessionId": "session-id", "TokenValue": "session-token", "StreamUrl": "wss://example"}


class _FakeBotoSession:
    def __init__(self, ssm: _FakeSSM) -> None:
        self._ssm = ssm
        self.kwargs: dict = {}

    def client(self, service: str, region_name: str | None = None) -> _FakeSSM:
        # One fake serves both clients: start_session (ssm) and describe_instances (ec2).
        assert service in ("ssm", "ec2")
        assert region_name == "ap-northeast-1"
        return self._ssm


class _FakeBoto3:
    def __init__(self, session: _FakeBotoSession) -> None:
        self.session = session

    def Session(self, **kwargs: Any) -> _FakeBotoSession:  # noqa: N802
        self.session.kwargs = kwargs
        return self.session


def _tunnel_config(**overrides: Any) -> EnclaveSsmTunnelConfig:
    base: dict[str, Any] = {
        "region": "ap-northeast-1",
        "target_instance_id": "i-bastion",
        "aws_secret": "aws-creds",
        "plugin_path": "/fake/session-manager-plugin",
        "idle_shutdown_s": 600,
    }
    base.update(overrides)
    return EnclaveSsmTunnelConfig(**base)


def _write_config(data_dir: Path, *, secrets_dir: str) -> None:
    config: dict = dict(DEFAULT_TEST_CONFIG)
    config["enclave"] = {"enabled": True, "secrets_dir": secrets_dir}
    (data_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    invalidate_cache()


@pytest.fixture(autouse=True)
def _reset_tunnels() -> None:
    ssm_tunnel._TUNNELS.clear()
    ssm_tunnel._LOCKS.clear()
    ssm_tunnel._REAPER_STARTED = False
    yield
    ssm_tunnel.stop_all_tunnels()
    ssm_tunnel._TUNNELS.clear()
    ssm_tunnel._LOCKS.clear()
    ssm_tunnel._REAPER_STARTED = False


def _setup(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    ssm: _FakeSSM | None = None,
) -> tuple[_FakeBotoSession, list[str]]:
    secrets_dir = data_dir / "secretstore"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / "aws-creds").write_text(
        json.dumps({"aws_access_key_id": "access", "aws_secret_access_key": "secret"}),
        encoding="utf-8",
    )
    _write_config(data_dir, secrets_dir=str(secrets_dir))

    boto_session = _FakeBotoSession(ssm or _FakeSSM())
    boto3_mod = _FakeBoto3(boto_session)
    monkeypatch.setitem(sys.modules, "boto3", boto3_mod)

    spawned: list[str] = []

    def _fake_start_plugin(config: EnclaveSsmTunnelConfig, session: dict, request: dict) -> _FakeProc:
        proc = _FakeProc(ssm_tunnel._plugin_command(config, session, request))
        spawned.append(json.dumps(proc.args))
        return proc

    monkeypatch.setattr(ssm_tunnel, "_start_plugin", _fake_start_plugin)
    monkeypatch.setattr(ssm_tunnel, "_free_port", lambda: 65432)
    monkeypatch.setattr(ssm_tunnel, "_port_open", lambda port: True)
    return boto_session, spawned


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_start_session_uses_configured_target_and_document(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boto_session, _ = _setup(data_dir, monkeypatch)

    port = ssm_tunnel.ensure_tunnel("main", _tunnel_config(), "rds.example", 3306)

    assert port == 65432
    assert len(boto_session._ssm.started) == 1
    started = boto_session._ssm.started[0]
    assert started["Target"] == "i-bastion"
    assert started["DocumentName"] == "AWS-StartPortForwardingSessionToRemoteHost"
    assert started["Parameters"] == {"host": ["rds.example"], "portNumber": ["3306"], "localPortNumber": ["65432"]}
    assert boto_session.kwargs["region_name"] == "ap-northeast-1"
    assert boto_session.kwargs["aws_access_key_id"] == "access"
    assert boto_session.kwargs["aws_secret_access_key"] == "secret"


def test_plugin_command_gets_session_output_not_aws_keys(data_dir: Path) -> None:  # noqa: ARG001
    config = _tunnel_config()
    args = ssm_tunnel._plugin_command(
        config,
        {"SessionId": "session-id", "TokenValue": "session-token", "StreamUrl": "wss://example"},
        {"Target": "i-bastion", "DocumentName": "AWS-StartPortForwardingSessionToRemoteHost", "Parameters": {}},
    )
    assert args[0] == "/fake/session-manager-plugin"
    response = json.loads(args[1])
    assert response["SessionId"] == "session-id"
    assert json.loads(args[5])["Target"] == "i-bastion"
    assert response["TokenValue"] == "session-token"
    assert response["StreamUrl"] == "wss://example"
    assert args[2] == "ap-northeast-1"
    assert args[3] == "StartSession"
    assert args[6] == "https://ssm.ap-northeast-1.amazonaws.com"
    # AWS keys must not appear anywhere on the plugin command line.
    assert "access" not in json.dumps(args)
    assert "secret" not in json.dumps(args)


def test_resolves_target_tag_to_instance(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boto_session, _ = _setup(data_dir, monkeypatch)
    config = _tunnel_config(target_instance_id=None, target_tag_name="example-bastion")

    ssm_tunnel.ensure_tunnel("main", config, "rds.example", 3306)

    assert boto_session._ssm.describes
    filters = boto_session._ssm.describes[0]["Filters"]
    assert {"Name": "tag:Name", "Values": ["example-bastion"]} in filters
    assert boto_session._ssm.started[0]["Target"] == "i-bastion"


def test_target_tag_zero_matches_raises(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(data_dir, monkeypatch, ssm=_FakeSSM(instances=[]))
    config = _tunnel_config(target_instance_id=None, target_tag_name="nope")
    with pytest.raises(ssm_tunnel.TunnelError):
        ssm_tunnel.ensure_tunnel("main", config, "rds.example", 3306)


def test_target_tag_multiple_matches_raises(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(data_dir, monkeypatch, ssm=_FakeSSM(multiple=True))
    config = _tunnel_config(target_instance_id=None, target_tag_name="dup")
    with pytest.raises(ssm_tunnel.TunnelError):
        ssm_tunnel.ensure_tunnel("main", config, "rds.example", 3306)


def test_tunnel_is_reused_within_idle_window(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boto_session, spawned = _setup(data_dir, monkeypatch)
    config = _tunnel_config()

    ssm_tunnel.ensure_tunnel("main", config, "rds.example", 3306)
    ssm_tunnel.ensure_tunnel("main", config, "rds.example", 3306)

    assert len(boto_session._ssm.started) == 1
    assert len(spawned) == 1


def test_dead_process_is_reestablished(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boto_session, _ = _setup(data_dir, monkeypatch)
    config = _tunnel_config()
    ssm_tunnel.ensure_tunnel("main", config, "rds.example", 3306)

    # Simulate the plugin process dying.
    tunnel = ssm_tunnel._TUNNELS["main"]
    tunnel.process.alive = False

    ssm_tunnel.ensure_tunnel("main", config, "rds.example", 3306)

    assert len(boto_session._ssm.started) == 2


def test_idle_tunnel_is_stopped(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boto_session, _ = _setup(data_dir, monkeypatch)
    config = _tunnel_config(idle_shutdown_s=1)
    ssm_tunnel.ensure_tunnel("main", config, "rds.example", 3306)

    tunnel = ssm_tunnel._TUNNELS["main"]
    tunnel.last_used -= 10

    ssm_tunnel.stop_idle_tunnels()

    assert "main" not in ssm_tunnel._TUNNELS
    assert tunnel.process.terminated is True
    # idle tunnel is re-established on next use
    port = ssm_tunnel.ensure_tunnel("main", config, "rds.example", 3306)
    assert port == 65432
    assert len(boto_session._ssm.started) == 2


def test_stop_tunnel_tears_down(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(data_dir, monkeypatch)
    config = _tunnel_config()
    ssm_tunnel.ensure_tunnel("main", config, "rds.example", 3306)

    ssm_tunnel.stop_tunnel("main")

    assert "main" not in ssm_tunnel._TUNNELS
