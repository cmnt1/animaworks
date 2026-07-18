from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Machine verification of task completion criteria.

Milestone tasks may carry ``meta.completion_criteria`` — a list of
machine-checkable conditions.  ``TaskQueueManager.update_status`` refuses
the transition to ``done`` while any criterion is unmet, so a task cannot
be closed by conversation alone ("報告済み" != done).

Criterion schema (each item is a dict with a ``type`` key):

- ``{"type": "path_exists", "path": "<abs path>"}``
- ``{"type": "file_contains", "path": "<abs path>", "pattern": "<regex>"}``
- ``{"type": "git_commit", "repo": "<abs path>", "branch": "<name>",
   "message_pattern": "<regex>", "min_count": 1}``
  Counts commits on ``branch`` whose subject matches ``message_pattern``
  (both optional; defaults: current branch, any message, min_count 1).
- ``{"type": "http_ok", "url": "<url>", "timeout_s": 5}``
- ``{"type": "openspec_tasks_checked", "tasks_md": "<abs path>",
   "pattern": "<regex>"}``
  Every ``- [ ] / - [x]`` checkbox line in ``tasks_md`` matching
  ``pattern`` must be checked.  Fails when no line matches.
- ``{"type": "channel_post", "channel": "finance", "sender": "<anima>",
   "pattern": "<regex>", "since_ts": "<ISO8601>"}``
  The shared channel log must contain a post from ``sender`` matching
  ``pattern`` at or after ``since_ts`` (both pattern and since_ts optional).
  Used for "report to the channel" obligations.

Verification is fail-closed: malformed criteria, unknown types, and
checker errors all count as unmet.
"""

import logging
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger("animaworks.task_verification")

_GIT_TIMEOUT_S = 15
_HTTP_DEFAULT_TIMEOUT_S = 5
_CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(.*)$")


def extract_criteria(meta: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return the completion_criteria list from task meta (empty when absent)."""
    if not isinstance(meta, dict):
        return []
    raw = meta.get("completion_criteria")
    if not isinstance(raw, list):
        return []
    return [c for c in raw if isinstance(c, dict)]


def verify_completion_criteria(criteria: list[dict[str, Any]]) -> list[str]:
    """Check every criterion and return failure messages (empty = all met)."""
    failures: list[str] = []
    for idx, criterion in enumerate(criteria):
        ctype = criterion.get("type")
        checker = _CHECKERS.get(ctype or "")
        if checker is None:
            failures.append(f"criterion[{idx}]: unknown type {ctype!r}")
            continue
        try:
            error = checker(criterion)
        except Exception as e:  # fail-closed
            error = f"checker error: {e}"
        if error:
            failures.append(f"criterion[{idx}] ({ctype}): {error}")
    return failures


def _check_path_exists(c: dict[str, Any]) -> str | None:
    path = c.get("path")
    if not path:
        return "missing 'path'"
    if not Path(path).exists():
        return f"path does not exist: {path}"
    return None


def _check_file_contains(c: dict[str, Any]) -> str | None:
    path = c.get("path")
    pattern = c.get("pattern")
    if not path or not pattern:
        return "missing 'path' or 'pattern'"
    p = Path(path)
    if not p.is_file():
        return f"file does not exist: {path}"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"cannot read {path}: {e}"
    if not re.search(pattern, text, flags=re.MULTILINE):
        return f"pattern {pattern!r} not found in {path}"
    return None


def _check_git_commit(c: dict[str, Any]) -> str | None:
    repo = c.get("repo")
    if not repo:
        return "missing 'repo'"
    if not Path(repo).exists():
        return f"repo does not exist: {repo}"
    branch = c.get("branch")
    ref = branch or "HEAD"
    cmd = ["git", "-C", str(repo), "log", "--format=%s", ref]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"git log failed: {e}"
    if proc.returncode != 0:
        return f"git log failed for ref {ref!r}: {(proc.stderr or '').strip()[:200]}"
    subjects = [line for line in proc.stdout.splitlines() if line.strip()]
    message_pattern = c.get("message_pattern")
    if message_pattern:
        subjects = [s for s in subjects if re.search(message_pattern, s)]
    min_count = int(c.get("min_count", 1))
    if len(subjects) < min_count:
        detail = f" matching {message_pattern!r}" if message_pattern else ""
        return f"found {len(subjects)} commit(s){detail} on {ref!r}, need {min_count}"
    return None


def _check_http_ok(c: dict[str, Any]) -> str | None:
    url = c.get("url")
    if not url:
        return "missing 'url'"
    timeout = float(c.get("timeout_s", _HTTP_DEFAULT_TIMEOUT_S))
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            status = getattr(resp, "status", 200)
    except (urllib.error.URLError, OSError, ValueError) as e:
        return f"request failed: {e}"
    if not 200 <= int(status) < 400:
        return f"unexpected HTTP status {status}"
    return None


def _check_openspec_tasks_checked(c: dict[str, Any]) -> str | None:
    tasks_md = c.get("tasks_md")
    pattern = c.get("pattern")
    if not tasks_md or not pattern:
        return "missing 'tasks_md' or 'pattern'"
    p = Path(tasks_md)
    if not p.is_file():
        return f"tasks file does not exist: {tasks_md}"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"cannot read {tasks_md}: {e}"
    matched = 0
    unchecked: list[str] = []
    for line in lines:
        m = _CHECKBOX_RE.match(line)
        if not m:
            continue
        if not re.search(pattern, m.group(2)):
            continue
        matched += 1
        if m.group(1) == " ":
            unchecked.append(m.group(2).strip()[:80])
    if matched == 0:
        return f"no checkbox matching {pattern!r} in {tasks_md}"
    if unchecked:
        return f"{len(unchecked)}/{matched} matching checkbox(es) still unchecked: {'; '.join(unchecked[:3])}"
    return None


def _check_channel_post(c: dict[str, Any]) -> str | None:
    import json

    channel = c.get("channel")
    sender = c.get("sender")
    if not channel or not sender:
        return "missing 'channel' or 'sender'"
    pattern = c.get("pattern")
    since_ts = c.get("since_ts") or ""

    from core.paths import get_shared_dir

    log_path = get_shared_dir() / "channels" / f"{channel}.jsonl"
    if not log_path.is_file():
        return f"channel log does not exist: {log_path}"
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"cannot read {log_path}: {e}"
    for line in lines:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (msg.get("from") or msg.get("sender") or msg.get("author")) != sender:
            continue
        ts = msg.get("ts") or msg.get("timestamp") or ""
        if since_ts and ts < since_ts:
            continue
        text = msg.get("text") or msg.get("content") or ""
        if pattern and not re.search(pattern, text):
            continue
        return None
    detail = f" matching {pattern!r}" if pattern else ""
    since = f" since {since_ts}" if since_ts else ""
    return f"no #{channel} post by {sender}{detail}{since}"


_CHECKERS = {
    "path_exists": _check_path_exists,
    "file_contains": _check_file_contains,
    "git_commit": _check_git_commit,
    "http_ok": _check_http_ok,
    "openspec_tasks_checked": _check_openspec_tasks_checked,
    "channel_post": _check_channel_post,
}
