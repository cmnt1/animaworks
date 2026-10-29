from __future__ import annotations

import tomllib
from pathlib import Path


def test_animaworks_tool_entrypoint_uses_cli_dispatcher() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["scripts"]["animaworks-tool"] == "cli.tool_dispatch:cli_dispatch"


def test_animaworks_tool_dispatcher_is_in_cli_layer() -> None:
    import core.integrations
    from cli.tool_dispatch import cli_dispatch

    assert callable(cli_dispatch)
    assert not hasattr(core.integrations, "cli_dispatch")
