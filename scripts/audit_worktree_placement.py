from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def parse_worktree_paths(output: str) -> tuple[Path, ...]:
    """Extract worktree paths from ``git worktree list --porcelain`` output."""
    return tuple(
        Path(line.removeprefix("worktree ")).resolve() for line in output.splitlines() if line.startswith("worktree ")
    )


def find_misplaced_worktrees(paths: tuple[Path, ...], data_dir: Path) -> tuple[Path, ...]:
    """Return worktrees outside the charter-approved locations."""
    if not paths:
        return ()
    repo = paths[0]
    feature_root = Path(f"{repo}-feat").resolve()
    data_dir = data_dir.expanduser().resolve()

    misplaced: list[Path] = []
    for path in paths:
        try:
            parts = path.relative_to(data_dir).parts
        except ValueError:
            parts = ()
        in_company_worktrees = (
            len(parts) >= 4 and parts[0] == "companies" and parts[2] == "shared" and parts[3] == "worktrees"
        )
        if path != repo and not path.is_relative_to(feature_root) and not in_company_worktrees:
            misplaced.append(path)
    return tuple(misplaced)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit git worktree placement against the AnimaWorks charter.")
    parser.add_argument("repos", nargs="+", type=Path, help="Repository paths to audit")
    args = parser.parse_args()
    data_dir = Path(os.environ.get("ANIMAWORKS_DATA_DIR", "~/.animaworks"))

    found_violation = False
    for repo in args.repos:
        result = subprocess.run(
            ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
        for path in find_misplaced_worktrees(parse_worktree_paths(result.stdout), data_dir):
            print(f"{repo}: {path}")
            found_violation = True
    return int(found_violation)


if __name__ == "__main__":
    raise SystemExit(main())
