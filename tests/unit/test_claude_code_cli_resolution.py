from __future__ import annotations

import pytest


def test_windows_candidate_discovery_can_skip_sdk_bundled(monkeypatch, tmp_path):
    from core.platform import claude_code

    bundled = tmp_path / "sdk" / "claude.exe"
    bundled.parent.mkdir()
    bundled.write_text("fake", encoding="utf-8")

    monkeypatch.setattr(claude_code.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(claude_code.shutil, "which", lambda _name: None)
    monkeypatch.setattr(claude_code, "_find_sdk_bundled_cli", lambda: str(bundled))

    assert str(bundled) in claude_code._iter_claude_candidates()
    assert str(bundled) not in claude_code._iter_claude_candidates(include_bundled=False)


def test_explicit_claude_code_path_takes_priority(monkeypatch, tmp_path):
    from core.platform import claude_code

    pinned = tmp_path / "claude_2.1.81_js_build.exe"
    npm = tmp_path / "appdata" / "npm" / "claude.cmd"
    pinned.write_text("fake", encoding="utf-8")
    npm.parent.mkdir(parents=True)
    npm.write_text("fake", encoding="utf-8")

    monkeypatch.setattr(claude_code.sys, "platform", "win32")
    monkeypatch.setenv("ANIMAWORKS_CLAUDE_CODE_PATH", str(pinned))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(claude_code.shutil, "which", lambda _name: None)
    monkeypatch.setattr(claude_code, "_find_sdk_bundled_cli", lambda: None)

    assert claude_code._iter_claude_candidates()[0] == str(pinned)


def test_sdk_options_reject_windows_without_external_cli(monkeypatch):
    from core.execution import _sdk_options
    from core.platform import claude_code

    seen: dict[str, bool] = {}

    def fake_get_claude_executable(*, include_bundled: bool = True):
        seen["include_bundled"] = include_bundled
        return None

    monkeypatch.setattr(_sdk_options.sys, "platform", "win32")
    monkeypatch.setattr(claude_code, "get_claude_executable", fake_get_claude_executable)
    monkeypatch.setattr(_sdk_options, "_cached_cli_path", None)
    monkeypatch.setattr(_sdk_options, "_cli_path_resolved", False)

    with pytest.raises(_sdk_options.AgentSDKCLIUnavailableError):
        _sdk_options._resolve_sdk_cli_path()

    assert seen["include_bundled"] is False
