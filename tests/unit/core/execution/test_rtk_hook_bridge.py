from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

_BRIDGE_PATH = Path(__file__).resolve().parents[4] / "core" / "execution" / "_rtk_hook_bridge.py"
_SPEC = importlib.util.spec_from_file_location("_rtk_hook_bridge_under_test", _BRIDGE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
bridge = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bridge)


def test_normalise_windows_paths_for_bash() -> None:
    command = r"cd E:\OneDriveBiz\Tools\abconfig && python C:\tmp\script.py"

    assert bridge._normalise_windows_paths_for_bash(command) == (
        "cd E:/OneDriveBiz/Tools/abconfig && python C:/tmp/script.py"
    )


def test_main_emits_normalized_command_when_rtk_has_no_rewrite(monkeypatch) -> None:
    payload = {"tool_input": {"command": r"cd E:\OneDriveBiz\Tools\abconfig"}}

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, "", "")

    stdin = io.StringIO(json.dumps(payload))
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    try:
        bridge.main()
    except SystemExit as exc:
        assert exc.code == 0

    result = json.loads(stdout.getvalue())
    updated = result["hookSpecificOutput"]["updatedInput"]
    assert updated["command"] == "cd E:/OneDriveBiz/Tools/abconfig"
    assert "permissionDecision" not in result["hookSpecificOutput"]


def test_main_emits_normalized_command_when_rtk_fails(monkeypatch) -> None:
    payload = {"tool_input": {"command": r"python E:\OneDriveBiz\Tools\abconfig\Cnct_Env.py"}}

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("rtk")

    stdin = io.StringIO(json.dumps(payload))
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    try:
        bridge.main()
    except SystemExit as exc:
        assert exc.code == 0

    result = json.loads(stdout.getvalue())
    updated = result["hookSpecificOutput"]["updatedInput"]
    assert updated["command"] == "python E:/OneDriveBiz/Tools/abconfig/Cnct_Env.py"


def test_main_keeps_rtk_rewrite_permission_decision(monkeypatch) -> None:
    payload = {"tool_input": {"command": r"git -C E:\OneDriveBiz\Tools\General\animaworks status"}}

    def fake_run(*args, **kwargs):
        assert args[0][-1] == "git -C E:/OneDriveBiz/Tools/General/animaworks status"
        return subprocess.CompletedProcess(args[0], 0, "rtk git status\n", "")

    stdin = io.StringIO(json.dumps(payload))
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    bridge.main()

    result = json.loads(stdout.getvalue())
    hook_output = result["hookSpecificOutput"]
    assert hook_output["updatedInput"]["command"] == "rtk git status"
    assert hook_output["permissionDecision"] == "allow"
