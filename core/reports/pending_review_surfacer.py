# -*- coding: utf-8 -*-
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Surface product drafts that are stuck in レビュー待ち back to their reviewer.

Daily auto-post reports are produced by cron (no delegate_task tracking entry),
so the generic delegation-recovery loop never re-engages the reviewer.  Without
an active nudge, a draft can sit at ``status: レビュー待ち`` until the reviewer's
next (possibly throttled) heartbeat happens to act on it — which is why some
days the report is posted and some days it silently stalls.

This module scans the products tree, finds drafts that are awaiting review past
a threshold, and enqueues an idempotent, urgent review task into the reviewer's
own task queue so the loop is actively closed instead of relying on chance.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("animaworks.review_surfacer")

JST = timezone(timedelta(hours=9))

# Environment-specific default; overridable via CLI / arg for tests.
DEFAULT_PRODUCT_ROOT = Path(r"E:\OneDriveBiz\Obsidian\_products")

REVIEW_KIND = "pending_product_review"
PENDING_STATUS = "レビュー待ち"
DEFAULT_OLDER_THAN_MINUTES = 30


def _read_frontmatter_block(path: Path, *, max_lines: int = 500) -> str:
    """Read only the leading ``---``…``---`` block, not the (potentially large) body.

    This runs over the whole _products tree every cron tick, so loading full
    report bodies just to inspect frontmatter is wasted I/O.  Returns the block
    (including both fences) or ``""`` if there is no closing fence within
    ``max_lines``.
    """
    try:
        with path.open("r", encoding="utf-8-sig", errors="ignore") as fh:
            first = fh.readline()
            if first.strip() != "---":
                return ""
            lines = [first]
            for _ in range(max_lines):
                line = fh.readline()
                if not line:
                    return ""  # EOF before closing fence
                lines.append(line)
                if line.strip() == "---":
                    return "".join(lines)
    except OSError:
        return ""
    return ""


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Minimal, dup-key-tolerant frontmatter parser (last value wins)."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    values: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if not line or line.startswith((" ", "\t", "-")) or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def _demojibake(value: str) -> str | None:
    """Best-effort recovery of a cp932-double-encoded JP string.

    The recurring corruption writes the file's UTF-8 bytes back through cp932,
    so ``レビュー待ち`` can land on disk as ``繝ｬ繝薙Η繝ｼ蠕・■``.  The corruption is often
    *lossy* (replacement chars), so this returns the recovered text only when the
    round-trip succeeds cleanly, else ``None`` — callers must tolerate ``None``.
    """
    if not value or value.isascii():
        return None
    try:
        recovered = value.encode("cp932").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    return recovered or None


# CJK glyphs produced when a UTF-8 JP lead byte (0xE3 → hiragana/katakana) is
# misread as cp932.  Empirically collected from observed corruptions (e.g.
# レビュー待ち → 繝ｬ繝薙Η繝ｼ蠕・■).  The half-width-katakana range in _looks_mojibake
# already catches most cases; this set is a backstop and can be extended as new
# corruptions surface.
_MOJIBAKE_LEAD_GLYPHS = frozenset("縺繧繝蜈蠎蠕陜隴髢郢譁蠑")


def _looks_mojibake(value: str) -> bool:
    """Detect UTF-8-as-cp932 mojibake without relying on reversibility.

    Such mojibake reliably injects half-width katakana (U+FF61–U+FF9F) and a small
    set of high-frequency CJK lead glyphs.  Legitimate clean statuses (レビュー待ち,
    完了, 下書き, …) contain neither, so this is high-precision.
    """
    if not value or value.isascii():
        return False
    for ch in value:
        if 0xFF61 <= ord(ch) <= 0xFF9F:  # half-width katakana — never in clean JP status
            return True
        if ch in _MOJIBAKE_LEAD_GLYPHS:
            return True
    return False


# Known-good statuses we must never treat as corrupt.
_CLEAN_STATUSES = {PENDING_STATUS, "完了", "下書き", "差し戻し", "確認待ち", "保留"}


def _status_is_pending(status: str) -> tuple[bool, bool]:
    """Return (needs_attention, is_corrupt) for a frontmatter status value.

    Catches the clean ``レビュー待ち`` *and* any mojibaked product status — a
    corrupted draft is invisible in the Obsidian ledger and crashes the
    deterministic review cron, so it must be surfaced for repair instead of
    silently stalling the daily report.
    """
    if status == PENDING_STATUS:
        return True, False
    if status not in _CLEAN_STATUSES and _looks_mojibake(status):
        return True, True
    return False, False


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt


def find_pending_reviews(
    products_root: Path,
    *,
    older_than_minutes: int = DEFAULT_OLDER_THAN_MINUTES,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return product drafts awaiting review past the staleness threshold."""
    now = now or datetime.now(JST)
    cutoff = now - timedelta(minutes=older_than_minutes)
    found: list[dict[str, Any]] = []
    if not products_root.exists():
        return found
    for path in products_root.rglob("*.md"):
        block = _read_frontmatter_block(path)
        if not block:
            continue
        fm = _parse_frontmatter(block)
        if fm.get("type") != "product":
            continue
        is_pending, is_corrupt = _status_is_pending(fm.get("status", ""))
        if not is_pending:
            continue
        reviewer = fm.get("reviewer", "")
        if not reviewer:
            continue
        if str(fm.get("confirmed", "")).lower() == "true":
            continue
        updated = _parse_dt(fm.get("updated", "")) or _parse_dt(fm.get("created", ""))
        if updated is not None and updated > cutoff:
            continue  # too fresh — give the normal flow a chance first
        title = fm.get("title", path.stem)
        found.append(
            {
                "path": str(path),
                "code": fm.get("code", path.stem),
                "title": _demojibake(title) or title if is_corrupt else title,
                "reviewer": reviewer,
                "assignee": fm.get("assignee", ""),
                "discord_thread_id": fm.get("review_discord_thread_id", ""),
                "report_date": fm.get("report_date", ""),
                "corrupt": is_corrupt,
            }
        )
    return found


def _build_instruction(item: dict[str, Any]) -> str:
    thread = item.get("discord_thread_id", "")
    thread_line = (
        f"Discordスレッド `{thread}` に完成本文を投稿する。" if thread else "指定の投稿先に完成本文を投稿する。"
    )
    corrupt_line = ""
    if item.get("corrupt"):
        corrupt_line = (
            "⚠ このファイルは frontmatter が文字化け（cp932 二重エンコード）しており、"
            "Obsidian の台帳（Base）からも見えなくなっています。"
            "まず Python で生バイトを読み、`encoding='utf-8'` で UTF-8 として書き戻して文字化けを修復し、"
            "`type: product` / `status: レビュー待ち` が正しく1個ずつ読めることを確認してから次に進んでください。\n"
        )
    return (
        f"成果物 {item['code']}（{item['title']}）が status:レビュー待ち のまま滞留しています。"
        f"ファイル: {item['path']}\n"
        f"{corrupt_line}"
        "次を1ターンで最後まで実行してください（『委任した』『追跡中』は完了報告として認められません）:\n"
        "1. 本文と数値を確認する。\n"
        "2. 問題なければ frontmatter を *インプレース編集* で status:完了 / submitted:報告日 に更新する。"
        "重複キーを追記しないこと。UTF-8 を壊さないこと（PowerShell の Set-Content/Add-Content を素で使わない。"
        "必要なら Python で encoding='utf-8' で書き戻す）。\n"
        f"3. {thread_line}\n"
        "4. 差し戻しが必要なら理由を明記して assignee に再依頼する。"
    )


def surface_pending_reviews(
    products_root: Path | None = None,
    animas_dir: Path | None = None,
    *,
    older_than_minutes: int = DEFAULT_OLDER_THAN_MINUTES,
    now: datetime | None = None,
    write_pending: bool = True,
) -> list[dict[str, Any]]:
    """Enqueue an idempotent urgent review task per stuck draft. Returns surfaced items."""
    from core.memory.task_queue import TaskQueueManager
    from core.paths import get_animas_dir

    products_root = products_root or DEFAULT_PRODUCT_ROOT
    animas_dir = animas_dir or get_animas_dir()

    surfaced: list[dict[str, Any]] = []
    for item in find_pending_reviews(products_root, older_than_minutes=older_than_minutes, now=now):
        reviewer = item["reviewer"]
        reviewer_dir = animas_dir / reviewer
        if not reviewer_dir.exists():
            logger.warning("review_surfacer: reviewer dir missing for %s (code=%s)", reviewer, item["code"])
            continue
        tqm = TaskQueueManager(reviewer_dir)
        code = item["code"]
        instruction = _build_instruction(item)

        def _already_open(task: Any, _code: str = code) -> bool:
            meta = getattr(task, "meta", None) or {}
            return meta.get("kind") == REVIEW_KIND and meta.get("product_code") == _code

        entry = tqm.add_task_if_absent(
            _already_open,
            source="anima",
            original_instruction=instruction,
            assignee=reviewer,
            summary=f"レビュー督促: {code} {item['title']}",
            deadline="2h",
            relay_chain=[],
            meta={
                "kind": REVIEW_KIND,
                "product_code": code,
                "product_path": item["path"],
                "discord_thread_id": item["discord_thread_id"],
                "report_date": item["report_date"],
            },
        )
        if entry is None:
            logger.info("review_surfacer: %s already has an open review task for %s", reviewer, code)
            continue

        task_desc = {
            "task_type": "llm",
            "task_id": entry.task_id,
            "title": entry.summary,
            "description": instruction,
            "context": "",
            "acceptance_criteria": [],
            "constraints": [],
            "file_paths": [item["path"]],
            "submitted_by": "review_surfacer",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "reply_to": "",
            "source": "review_surfacer",
            "working_directory": "",
            "priority": "urgent",
        }
        try:
            tqm.update_meta(entry.task_id, {"task_desc": task_desc})
        except Exception:
            logger.warning("review_surfacer: failed to persist task_desc for %s", entry.task_id, exc_info=True)
        if write_pending:
            try:
                from core.urgent import add_urgent

                add_urgent(reviewer_dir, entry.task_id, note="pending product review")
            except Exception:
                logger.debug("review_surfacer: urgent registration skipped for %s", reviewer, exc_info=True)
            pending_dir = reviewer_dir / "state" / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)
            (pending_dir / f"{entry.task_id}.json").write_text(
                json.dumps(task_desc, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        surfaced.append({**item, "task_id": entry.task_id})
        logger.info("review_surfacer: surfaced %s to %s (task=%s)", code, reviewer, entry.task_id)
    return surfaced


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Surface レビュー待ち product drafts to their reviewer.")
    parser.add_argument("--products-root", type=Path, default=DEFAULT_PRODUCT_ROOT)
    parser.add_argument("--older-than-minutes", type=int, default=DEFAULT_OLDER_THAN_MINUTES)
    parser.add_argument("--dry-run", action="store_true", help="List stuck drafts without enqueuing tasks.")
    args = parser.parse_args(argv)

    if args.dry_run:
        items = find_pending_reviews(args.products_root, older_than_minutes=args.older_than_minutes)
        print(json.dumps({"status": "dry_run", "pending": items}, ensure_ascii=False, indent=2))
        return 0

    surfaced = surface_pending_reviews(args.products_root, older_than_minutes=args.older_than_minutes)
    print(json.dumps({"status": "done", "surfaced": surfaced}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    PROJECT_DIR = Path(__file__).resolve().parents[2]
    if str(PROJECT_DIR) not in sys.path:
        sys.path.insert(0, str(PROJECT_DIR))
    raise SystemExit(main())
