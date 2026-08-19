from __future__ import annotations

from pathlib import Path

from scripts.audit_worktree_placement import find_misplaced_worktrees, parse_worktree_paths


def test_parse_and_find_misplaced_worktrees(tmp_path: Path) -> None:
    repo = tmp_path / "project"
    paths = parse_worktree_paths(
        "\n".join(
            (
                f"worktree {repo}",
                "HEAD abc123",
                "branch refs/heads/main",
                "",
                f"worktree {repo}-feat/charter",
                "HEAD def456",
                "",
                f"worktree {tmp_path}/data/companies/acme/shared/worktrees/review",
                "HEAD 012345",
                "",
                f"worktree {tmp_path}/elsewhere/bad",
            )
        )
    )

    assert find_misplaced_worktrees(paths, tmp_path / "data") == ((tmp_path / "elsewhere/bad").resolve(),)
