from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "enclave" / "egress_firewall.py"


@pytest.fixture
def firewall(monkeypatch: pytest.MonkeyPatch):
    spec = importlib.util.spec_from_file_location("egress_firewall", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_aws_ranges", lambda region: (["192.0.2.0/24"], ["2001:db8::/32"]))
    return module


def test_only_the_enclave_uid_enters_the_restricting_chain(firewall) -> None:
    ruleset = firewall.build_ruleset(993, "ap-northeast-1", [18610])
    output_chain = ruleset.split("chain output {", 1)[1].split("}", 1)[0]
    # Socketless packets (FIN/ACK of closed sockets) never match skuid, so a
    # positive match keeps other users' traffic out of the reject path.
    assert "meta skuid 993 jump enclave" in output_chain
    assert "reject" not in output_chain
    assert "skuid !=" not in ruleset


def test_log_is_rate_limited_before_logging(firewall) -> None:
    ruleset = firewall.build_ruleset(993, "ap-northeast-1", [18610])
    log_line = next(line for line in ruleset.splitlines() if "log prefix" in line)
    assert log_line.strip().startswith("limit rate")
    assert ruleset.rstrip().splitlines()[-3].strip() == "reject"
