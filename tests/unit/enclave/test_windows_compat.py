"""Optional Linux enclaves must not prevent a normal Windows server from booting."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.config.schemas import AnimaWorksConfig
from core.enclave import EnclaveViolationError, collect_enclave_violations, enforce_enclave_runtime


@pytest.mark.asyncio
async def test_disabled_gateway_can_be_imported_started_and_stopped(tmp_path):
    from core.enclave.gateway_server import start_gateway, stop_gateway

    app = SimpleNamespace(state=SimpleNamespace())
    config = AnimaWorksConfig()
    with (
        patch("core.config.load_config", return_value=config),
        patch("core.paths.get_data_dir", return_value=tmp_path),
        patch("core.enclave.gateway_server.prepare_socket") as prepare,
    ):
        await start_gateway(app)
        await stop_gateway(app)
        prepare.assert_not_called()
    assert app.state.enclave_gateway is None
    assert app.state.enclave_gateway_task is None


def test_windows_accepts_normal_mode_and_rejects_enabled_enclave_before_side_effects(tmp_path, monkeypatch):
    before = set(tmp_path.iterdir())
    monkeypatch.setattr("core.enclave.guards.sys.platform", "win32")
    config = AnimaWorksConfig()
    assert collect_enclave_violations(config, tmp_path, host="127.0.0.1") == []
    enforce_enclave_runtime(config, tmp_path, host="127.0.0.1")
    config.enclave.enabled = True
    with pytest.raises(EnclaveViolationError, match="requires Linux"):
        enforce_enclave_runtime(config, tmp_path, host="127.0.0.1")
    assert set(tmp_path.iterdir()) == before


def test_gateway_without_peer_credentials_refuses_before_creating_socket(tmp_path, monkeypatch):
    before = set(tmp_path.iterdir())
    from core.enclave import gateway_server
    from core.enclave.config import EnclaveConfig

    monkeypatch.delattr(gateway_server.socket, "SO_PEERCRED", raising=False)
    config = EnclaveConfig(socket_path=str(tmp_path / "socket-dir" / "enclave.sock"))
    with pytest.raises(EnclaveViolationError, match="requires Linux"):
        gateway_server.prepare_socket(config)
    assert gateway_server.read_peercred(object()) is None
    assert set(tmp_path.iterdir()) == before


def test_ssm_tunnel_import_and_nonlinux_reservation_are_safe(tmp_path, monkeypatch):
    before = set(tmp_path.iterdir())
    import importlib
    import sys

    from core.enclave import ssm_tunnel
    from core.enclave.config import EnclaveSsmTunnelConfig

    monkeypatch.setitem(sys.modules, "fcntl", None)
    importlib.reload(ssm_tunnel)
    monkeypatch.setattr(ssm_tunnel.sys, "platform", "win32")
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)
    config = EnclaveSsmTunnelConfig(
        region="ap-northeast-1", aws_secret="test", target_instance_id="i-test", local_port=33061
    )
    with pytest.raises(ssm_tunnel.TunnelError, match="require Linux"):
        ssm_tunnel._reserve_port(config)
    assert set(tmp_path.iterdir()) == before
