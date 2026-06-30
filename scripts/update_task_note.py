# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""update_task_note.py — deterministic, UTF-8-safe frontmatter field updater for
Obsidian `_notes/Projects` task notes.

Why this exists
---------------
The weekly meeting/planning agent writes plan fields (`次アクション期限`,
`今週タスク`, …) back into `_notes/Projects/*.md` task notes. On JP Windows a bare
`open()` / PowerShell `Set-Content` defaults to cp932/ANSI, so reading a UTF-8
note as cp932 (or writing UTF-8 text through cp932) double-encodes the Japanese
frontmatter (`カテゴリ: 文芸` → `繧ｫ繝・ざ繝ｪ: 譁・敢`). A corrupted note loses its
keys and silently drops out of the Obsidian Base / meeting picker.

This collapses the whole read-modify-write surface to one tested function that
is UTF-8 on both ends: read `utf-8-sig` (tolerate a stray BOM), edit only the
named frontmatter scalars **in place** (existing key → value rewritten, never
duplicated; body preserved byte-for-byte), write `utf-8` with LF and no BOM,
then read-after-write verify the new values landed and no mojibake was
introduced.

Contract
--------
    python scripts/update_task_note.py --note <path-to.md> \
        --set "次アクション期限=2026-07-10" --set "今週タスク=初稿を仕上げる"

`--set KEY=VALUE` may be repeated. Output is a result JSON on stdout:

    {"ok": true, "note": "...", "updated": {"次アクション期限": "..."},
     "added": [...], "checks": {...}}

Exit code 0 only when every field verified and the note is not corrupt; non-zero
otherwise, so a cron / agent can detect a failed write instead of trusting a
self-report.

A note whose frontmatter is *already* cp932-mojibaked is refused (corrupt=True,
non-zero exit) rather than written over — the original bytes are already lost
and writing would only entrench the damage; the corruption must be repaired
from a clean source first.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Runnable both as `python scripts/update_task_note.py` and imported in tests;
# ensure the repo root is importable so the shared mojibake detector resolves
# even without the editable install on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Reuse the single source of truth for cp932-mojibake detection so this tool and
# the report surfacer can't diverge as the glyph set is extended over time.
from core.reports.pending_review_surfacer import _looks_mojibake as looks_mojibake


def _needs_quoting(value: str) -> bool:
    if value == "" or value != value.strip():
        return True
    if value[0] in "#&*!|>%@`\"'[]{},":
        return True
    return ": " in value or value.endswith(":")


def _format_scalar(value: str) -> str:
    if not _needs_quoting(value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class TaskNoteError(Exception):
    """Raised when a note cannot be updated safely."""


def _split_frontmatter(text: str) -> tuple[list[str], list[str], list[str]]:
    """Return (pre, fm_body, post) line lists.

    ``pre`` holds the opening ``---`` (and anything before it, normally empty),
    ``fm_body`` the frontmatter lines between the fences, ``post`` the closing
    ``---`` onward (the note body). Raises if there is no frontmatter block.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise TaskNoteError("note has no opening frontmatter fence")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[:1], lines[1:i], lines[i:]
    raise TaskNoteError("note has no closing frontmatter fence")


def _parse_key(line: str) -> str | None:
    stripped = line.lstrip()
    if not stripped or stripped.startswith("#") or ":" not in line:
        return None
    # Only treat top-level (unindented) keys as frontmatter scalars we own.
    if line[:1] in (" ", "\t"):
        return None
    return line.split(":", 1)[0].strip()


def apply_updates(text: str, updates: dict[str, str]) -> tuple[str, dict[str, str], list[str]]:
    """Rewrite the named frontmatter scalars in ``text`` and return the new text.

    Existing keys are updated in place; missing keys are appended just before the
    closing fence. The body is preserved exactly. Returns (new_text, updated,
    added).
    """
    pre, fm_body, post = _split_frontmatter(text)

    for key, value in tuple(updates.items()):
        if looks_mojibake(key) or looks_mojibake(value):
            raise TaskNoteError(f"refusing to write mojibaked field: {key!r}")

    remaining = dict(updates)
    updated: dict[str, str] = {}
    new_fm: list[str] = []
    i = 0
    while i < len(fm_body):
        line = fm_body[i]
        key = _parse_key(line)
        if key is not None and key in remaining:
            value = remaining.pop(key)
            new_fm.append(f"{key}: {_format_scalar(value)}")
            updated[key] = value
            # Drop the old value's indented continuation (block scalar / YAML
            # list items) so replacing a multi-line value with a scalar can't
            # leave orphaned lines that corrupt the frontmatter.
            i += 1
            while i < len(fm_body) and fm_body[i][:1] in (" ", "\t"):
                i += 1
            continue
        new_fm.append(line)
        i += 1

    added = list(remaining)
    for key in added:
        new_fm.append(f"{key}: {_format_scalar(remaining[key])}")
        updated[key] = remaining[key]

    new_text = "\n".join([*pre, *new_fm, *post])
    return new_text, updated, added


def read_note(path: Path) -> str:
    """Read a note as UTF-8, tolerating a stray BOM."""
    return path.read_bytes().decode("utf-8-sig")


def write_note(path: Path, text: str) -> None:
    """Write a note as UTF-8 with LF newlines and no BOM."""
    path.write_text(text, encoding="utf-8", newline="\n")


def update_task_note(path: Path, updates: dict[str, str]) -> dict[str, object]:
    """Apply ``updates`` to the task note at ``path`` and verify the result.

    Returns a result dict. ``ok`` is True only when every field landed and the
    note's frontmatter is free of mojibake on read-back.
    """
    res: dict[str, object] = {
        "note": str(path),
        "updated": {},
        "added": [],
        "checks": {},
        "ok": False,
    }
    if not path.exists():
        res["error"] = f"note not found: {path}"
        return res

    try:
        original = read_note(path)
    except (OSError, UnicodeDecodeError) as exc:
        res["error"] = f"unreadable: {exc}"
        return res

    # Refuse to overwrite an already-corrupt note: its bytes are lost and a write
    # would only entrench the damage. Surface it so it can be repaired first.
    pre, fm_body, _ = _split_frontmatter_safe(original)
    if any(looks_mojibake(line) for line in fm_body):
        res["error"] = "note frontmatter is already cp932-corrupt; repair before writing"
        res["corrupt"] = True
        return res

    try:
        new_text, updated, added = apply_updates(original, updates)
    except TaskNoteError as exc:
        res["error"] = str(exc)
        return res

    write_note(path, new_text)

    # Read-after-write verification: re-read from disk and confirm the new values
    # are present and nothing mojibaked.
    verify = read_note(path)
    _, verify_fm, _ = _split_frontmatter_safe(verify)
    fm_props = {k: v for k, v in (_parse_kv(line) for line in verify_fm) if k is not None}
    values_ok = all(fm_props.get(k) == v for k, v in updated.items())
    no_mojibake = not any(looks_mojibake(k) or looks_mojibake(v) for k, v in fm_props.items())
    res["updated"] = updated
    res["added"] = added
    res["checks"] = {"values_written": values_ok, "no_mojibake": no_mojibake}
    res["ok"] = values_ok and no_mojibake
    return res


def _split_frontmatter_safe(text: str) -> tuple[list[str], list[str], list[str]]:
    try:
        return _split_frontmatter(text)
    except TaskNoteError:
        return [], [], []


def _parse_kv(line: str) -> tuple[str | None, str]:
    key = _parse_key(line)
    if key is None:
        return None, ""
    value = line.split(":", 1)[1].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        inner = value[1:-1]
        if value[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        value = inner
    return key, value


def _parse_set(pairs: list[str]) -> dict[str, str]:
    updates: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--set expects KEY=VALUE, got: {pair!r}")
        key, value = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise SystemExit(f"--set has empty key: {pair!r}")
        updates[key] = value
    return updates


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="UTF-8-safe Obsidian task-note frontmatter updater")
    p.add_argument("--note", required=True, help="path to the _notes/Projects task note (.md)")
    p.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="frontmatter field to set (repeatable)",
    )
    args = p.parse_args(argv)

    updates = _parse_set(args.set)
    if not updates:
        raise SystemExit("nothing to do: pass at least one --set KEY=VALUE")

    result = update_task_note(Path(args.note), updates)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
