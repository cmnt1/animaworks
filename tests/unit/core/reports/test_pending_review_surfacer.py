from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.memory.task_queue import TaskQueueManager
from core.reports.pending_review_surfacer import (
    PENDING_STATUS,
    REVIEW_KIND,
    _looks_mojibake,
    find_pending_reviews,
    surface_pending_reviews,
)

# The real observed corruption of レビュー待ち seen in P-00148's frontmatter
# (UTF-8 bytes re-encoded through cp932; lossy, so not cleanly reversible).
MOJIBAKE_PENDING = "繝ｬ繝薙Η繝ｼ蠕・■"

JST = timezone(timedelta(hours=9))


def _write_product(
    products_root: Path,
    name: str,
    *,
    type_: str = "product",
    status: str = "レビュー待ち",
    reviewer: str = "sakura",
    confirmed: str = "false",
    updated: str = "2026-06-20T06:45:08+09:00",
    code: str | None = None,
) -> Path:
    path = products_root / "Property" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"type: {type_}", f"code: {code or name}", "title: テストレポート"]
    lines.append(f"status: {status}")
    if reviewer:
        lines.append(f"reviewer: {reviewer}")
    lines.append("assignee: hikaru")
    lines.append('review_discord_thread_id: "12345"')
    lines.append("report_date: 2026-06-20")
    lines.append(f"confirmed: {confirmed}")
    lines.append(f"updated: {updated}")
    lines.append("---")
    lines.append("")
    lines.append("# body")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _now() -> datetime:
    return datetime(2026, 6, 20, 12, 0, tzinfo=JST)


def test_find_pending_reviews_selects_only_stale_pending(tmp_path: Path) -> None:
    products = tmp_path / "_products"
    _write_product(products, "P-1", status="レビュー待ち")
    _write_product(products, "P-2", status="完了")  # not pending
    _write_product(products, "P-3", status="レビュー待ち", confirmed="true")  # already confirmed
    _write_product(products, "P-4", status="レビュー待ち", type_="note")  # not a product
    _write_product(products, "P-5", status="レビュー待ち", reviewer="")  # no reviewer
    _write_product(products, "P-6", status="レビュー待ち", updated="2026-06-20T11:55:00+09:00")  # too fresh

    found = find_pending_reviews(products, older_than_minutes=30, now=_now())

    assert [item["code"] for item in found] == ["P-1"]


def test_looks_mojibake_distinguishes_clean_from_corrupt() -> None:
    assert _looks_mojibake(MOJIBAKE_PENDING) is True
    assert _looks_mojibake(PENDING_STATUS) is False  # clean レビュー待ち
    assert _looks_mojibake("完了") is False
    assert _looks_mojibake("plain-ascii") is False


def test_find_pending_reviews_catches_mojibake_draft(tmp_path: Path) -> None:
    # A corrupted draft is invisible in the ledger AND crashes the review cron;
    # the surfacer must still catch it (status reads as mojibake, not レビュー待ち).
    products = tmp_path / "_products"
    _write_product(products, "P-7", status=MOJIBAKE_PENDING)

    found = find_pending_reviews(products, older_than_minutes=30, now=_now())

    assert [item["code"] for item in found] == ["P-7"]
    assert found[0]["corrupt"] is True


def test_find_pending_reviews_tolerates_duplicate_keys(tmp_path: Path) -> None:
    products = tmp_path / "_products"
    path = products / "Property" / "P-9.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Simulate the corruption mode: duplicate status keys (last wins -> 完了 -> skipped)
    path.write_text(
        "---\ntype: product\ncode: P-9\nstatus: レビュー待ち\nstatus: 完了\nreviewer: sakura\n"
        "updated: 2026-06-20T06:45:08+09:00\n---\n# body\n",
        encoding="utf-8",
    )
    found = find_pending_reviews(products, older_than_minutes=30, now=_now())
    assert found == []


def test_surface_pending_reviews_enqueues_once(tmp_path: Path) -> None:
    products = tmp_path / "_products"
    animas = tmp_path / "animas"
    (animas / "sakura" / "state").mkdir(parents=True)
    _write_product(products, "P-00148", code="P-00148")

    surfaced = surface_pending_reviews(
        products, animas, older_than_minutes=30, now=_now(), write_pending=False
    )
    assert [s["code"] for s in surfaced] == ["P-00148"]

    tqm = TaskQueueManager(animas / "sakura")
    review_tasks = [
        t for t in tqm.list_tasks() if (t.meta or {}).get("kind") == REVIEW_KIND
    ]
    assert len(review_tasks) == 1
    assert review_tasks[0].meta["product_code"] == "P-00148"
    task_desc = review_tasks[0].meta["task_desc"]
    assert task_desc["priority"] == "urgent"
    assert task_desc["closure_required"] is True
    assert any("task_closure" in criterion for criterion in task_desc["acceptance_criteria"])

    # Idempotent: running again does not create a duplicate.
    again = surface_pending_reviews(
        products, animas, older_than_minutes=30, now=_now(), write_pending=False
    )
    assert again == []
    review_tasks_after = [
        t for t in tqm.list_tasks() if (t.meta or {}).get("kind") == REVIEW_KIND
    ]
    assert len(review_tasks_after) == 1
