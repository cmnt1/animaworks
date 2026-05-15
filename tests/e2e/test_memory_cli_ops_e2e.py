"""E2E coverage for memory CLI operational status output."""

from __future__ import annotations

import argparse
import json

import pytest


@pytest.mark.e2e
def test_memory_status_json_reports_effective_backends_e2e(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from cli.commands.memory_cmd import register_memory_command
    from core.config.models import invalidate_cache

    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    invalidate_cache()
    try:
        animas_dir = tmp_path / "animas"
        (animas_dir / "legacy-bot").mkdir(parents=True)
        sakura_dir = animas_dir / "sakura"
        sakura_dir.mkdir()
        (sakura_dir / "status.json").write_text(json.dumps({"memory_backend": "neo4j"}), encoding="utf-8")

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        register_memory_command(subparsers)
        args = parser.parse_args(["memory", "status", "--json"])

        args.func(args)

        payload = json.loads(capsys.readouterr().out)
        by_name = {entry["name"]: entry for entry in payload["animas"]}
        assert payload["global_backend"] == "legacy"
        assert payload["summary"]["backends"] == {"legacy": 1, "neo4j": 1}
        assert by_name["legacy-bot"]["effective_backend"] == "legacy"
        assert by_name["legacy-bot"]["source"] == "global"
        assert by_name["sakura"]["effective_backend"] == "neo4j"
        assert by_name["sakura"]["source"] == "per-anima"
        assert "password" not in json.dumps(payload)
    finally:
        invalidate_cache()
