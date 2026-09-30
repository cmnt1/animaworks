"""Ratchet tests for JSON-file writes and direct status.json references.

Run ``python -m tests.unit.test_code_gates --update`` from the repository root
to regenerate the reviewed file/count baselines after intentional cleanup.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("core", "cli", "server")
BASELINE_PATH = Path(__file__).with_name("code_gates_baseline.json")


def _python_files() -> list[Path]:
    return sorted(
        path for package in SCAN_ROOTS for path in (ROOT / package).rglob("*.py") if "__pycache__" not in path.parts
    )


def _is_json_dumps_call(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "dumps"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "json"
    )


@lru_cache(maxsize=1)
def _parsed_python_files() -> tuple[tuple[Path, ast.Module], ...]:
    return tuple((path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))) for path in _python_files())


@lru_cache(maxsize=1)
def _collect_code_gate_data() -> tuple[dict[str, int], list[str]]:
    """Collect both gates in one AST pass to keep the checks fast."""
    counts: Counter[str] = Counter()
    status_files = []
    for path, tree in _parsed_python_files():
        relative_path = path.relative_to(ROOT).as_posix()
        has_status_literal = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "status.json":
                has_status_literal = True
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "write_text"
                and node.args
                and _is_json_dumps_call(node.args[0])
            ):
                counts[relative_path] += 1
        if has_status_literal:
            status_files.append(relative_path)
    return dict(sorted(counts.items())), status_files


def collect_write_text_json_dumps() -> dict[str, int]:
    """Count calls whose first write_text argument is json.dumps(...)."""
    return _collect_code_gate_data()[0]


def collect_status_json_literal_files() -> list[str]:
    """Return files containing an actual string literal equal to status.json."""
    return _collect_code_gate_data()[1]


def _current_baseline() -> dict[str, object]:
    return {
        "write_text_json_dumps": collect_write_text_json_dumps(),
        "status_json_literal_files": collect_status_json_literal_files(),
    }


def _read_baseline() -> dict[str, object]:
    if not BASELINE_PATH.exists():
        raise AssertionError(
            f"Missing code gate baseline: {BASELINE_PATH}; run python -m tests.unit.test_code_gates --update"
        )
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def update_baseline() -> None:
    """Rewrite baselines from current code; review the diff before accepting it."""
    BASELINE_PATH.write_text(json.dumps(_current_baseline(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote code gate baseline to {BASELINE_PATH}")


def test_write_text_json_dumps_matches_baseline() -> None:
    expected = _read_baseline()["write_text_json_dumps"]
    actual = collect_write_text_json_dumps()
    assert actual == expected, (
        "write_text(json.dumps(...)) file/count baseline changed; update "
        "tests/unit/code_gates_baseline.json after reviewing the change.\n"
        f"Expected: {expected}\nActual: {actual}"
    )


def test_status_json_literal_files_match_baseline() -> None:
    expected = _read_baseline()["status_json_literal_files"]
    actual = collect_status_json_literal_files()
    assert actual == expected, (
        'Files containing the "status.json" string literal changed; update '
        "tests/unit/code_gates_baseline.json after reviewing the change.\n"
        f"Expected: {expected}\nActual: {actual}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="regenerate the reviewed code-gate baseline")
    args = parser.parse_args()
    if args.update:
        update_baseline()
    else:
        parser.error("Use --update to regenerate the baseline, or run this module with pytest")


if __name__ == "__main__":
    main()
