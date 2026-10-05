from __future__ import annotations

import pytest

from cli.parser import build_parser


@pytest.mark.parametrize("command", ["create-anima", "list", "gateway", "worker", "migrate-cron"])
def test_retired_top_level_commands_are_invalid(command: str) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([command])


def test_migrate_resync_db_option_is_invalid() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["migrate", "--resync-db"])


def test_replacement_commands_remain_valid() -> None:
    create_args = build_parser().parse_args(["anima", "create", "--name", "alice"])
    migrate_args = build_parser().parse_args(["migrate", "--dry-run"])
    status_args = build_parser().parse_args(["status"])

    assert create_args.command == "anima"
    assert create_args.anima_command == "create"
    assert migrate_args.command == "migrate"
    assert migrate_args.dry_run is True
    assert status_args.command == "status"


def test_tool_cli_does_not_forward_retired_commands() -> None:
    from cli.tool_dispatch import MAIN_CLI_COMMANDS

    retired = {"create-anima", "list", "migrate-cron"}
    assert retired.isdisjoint(MAIN_CLI_COMMANDS)
    assert "status" in MAIN_CLI_COMMANDS
