from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.reports.pending_review_surfacer import (
    PENDING_STATUS,
    REVIEW_KIND,
    _looks_mojibake,
    find_pending_reviews,
    surface_pending_reviews,
)
from core.tasks.queue import TaskQueueManager

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
    review_hold: str | None = None,
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
    if review_hold is not None:
        lines.append(f"review_hold: {review_hold}")
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

    surfaced = surface_pending_reviews(products, animas, older_than_minutes=30, now=_now(), write_pending=False)
    assert [s["code"] for s in surfaced] == ["P-00148"]

    tqm = TaskQueueManager(animas / "sakura")
    review_tasks = [t for t in tqm.list_tasks() if (t.meta or {}).get("kind") == REVIEW_KIND]
    assert len(review_tasks) == 1
    assert review_tasks[0].meta["product_code"] == "P-00148"
    task_desc = review_tasks[0].meta["task_desc"]
    assert task_desc["priority"] == "urgent"
    assert task_desc["closure_required"] is True
    assert any("task_closure" in criterion for criterion in task_desc["acceptance_criteria"])

    # Idempotent: running again does not create a duplicate.
    again = surface_pending_reviews(products, animas, older_than_minutes=30, now=_now(), write_pending=False)
    assert again == []
    review_tasks_after = [t for t in tqm.list_tasks() if (t.meta or {}).get("kind") == REVIEW_KIND]
    assert len(review_tasks_after) == 1


def test_surface_publishes_runnable_input_after_sqlite_migration(tmp_path: Path) -> None:
    products = tmp_path / "_products"
    animas = tmp_path / "animas"
    reviewer_dir = animas / "sakura"
    (reviewer_dir / "state").mkdir(parents=True)
    _write_product(products, "P-00400", code="P-00400")
    tqm = TaskQueueManager(reviewer_dir)
    # Import the legacy queue before the surfacer runs, as on the live server.
    tqm.store.import_legacy(reviewer_dir)
    surfaced = surface_pending_reviews(products, animas, older_than_minutes=30, now=_now())
    pending = tqm.store.pending("sakura")
    assert [p["task_id"] for p in pending] == [surfaced[0]["task_id"]]
    assert pending[0]["closure_required"] is True
    assert "review_hold: false" in pending[0]["description"]
    assert surface_pending_reviews(products, animas, older_than_minutes=30, now=_now()) == []
    assert len(tqm.store.pending("sakura")) == 1


def test_scoped_local_recovery_does_not_notify_other_products(tmp_path: Path) -> None:
    products = tmp_path / "_products"
    animas = tmp_path / "animas"
    (animas / "sakura" / "state").mkdir(parents=True)
    path = _write_product(products, "P-00401", code="P-00401")
    path.write_text(
        path.read_text(encoding="utf-8").replace("type: product", "type: product\ntask_code: PTY-ANJO-1K-DAILY"),
        encoding="utf-8",
    )
    _write_product(products, "P-00402", code="P-00402")
    result = surface_pending_reviews(products, animas, now=_now(), task_code="PTY-ANJO-1K-DAILY", local_only=True)
    assert [item["code"] for item in result] == ["P-00401"]
    pending = TaskQueueManager(animas / "sakura").store.pending("sakura")
    assert len(pending) == 1
    assert "完成本文を投稿する" not in pending[0]["description"]
    assert "外部への投稿・通知は行わない" in pending[0]["description"]
    assert "no Discord" in pending[0]["constraints"][0]


def test_scoped_recovery_reviews_pending_even_if_owner_confirmed(tmp_path: Path) -> None:
    products = tmp_path / "_products"
    animas = tmp_path / "animas"
    (animas / "sakura" / "state").mkdir(parents=True)
    path = _write_product(products, "P-00403", code="P-00403", confirmed="true")
    path.write_text(
        path.read_text(encoding="utf-8").replace("type: product", "type: product\ntask_code: PROP-07"), encoding="utf-8"
    )
    result = surface_pending_reviews(products, animas, now=_now(), task_code="PROP-07", local_only=True)
    assert [item["code"] for item in result] == ["P-00403"]
    assert len(TaskQueueManager(animas / "sakura").store.pending("sakura")) == 1
    assert "confirmed: true" in path.read_text(encoding="utf-8")


# ── review_hold guard (task 6d01f7377492) ──────────────────────


def test_review_hold_state_is_fail_closed() -> None:
    from core.reports.pending_review_surfacer import HOLD_HELD, HOLD_RELEASED, HOLD_UNKNOWN, review_hold_state

    assert review_hold_state({"review_hold": "true"}) == HOLD_HELD
    assert review_hold_state({"review_hold": "True  # sakura"}) == HOLD_HELD
    assert review_hold_state({"review_hold": "false"}) == HOLD_RELEASED
    assert review_hold_state({}) == HOLD_UNKNOWN
    assert review_hold_state({"review_hold": ""}) == HOLD_UNKNOWN
    assert review_hold_state({"review_hold": "maybe"}) == HOLD_UNKNOWN


def test_held_draft_is_not_surfaced_and_reported(tmp_path: Path) -> None:
    products = tmp_path / "_products"
    _write_product(products, "P-00383", code="P-00383", review_hold="true")
    _write_product(products, "P-00390", code="P-00390", review_hold="false")
    held: list = []

    found = find_pending_reviews(products, older_than_minutes=30, now=_now(), held_out=held)

    assert [item["code"] for item in found] == ["P-00390"]
    assert [item["code"] for item in held] == ["P-00383"]


def test_held_draft_enqueues_nothing_and_file_unchanged(tmp_path: Path) -> None:
    products = tmp_path / "_products"
    animas = tmp_path / "animas"
    (animas / "sakura" / "state").mkdir(parents=True)
    path = _write_product(products, "P-00384", code="P-00384", review_hold="true")
    before = path.read_bytes()

    surfaced = surface_pending_reviews(products, animas, older_than_minutes=30, now=_now(), write_pending=True)

    assert surfaced == []
    assert TaskQueueManager(animas / "sakura").list_tasks() == []
    assert not (animas / "sakura" / "state" / "pending").exists()
    assert path.read_bytes() == before


def _surfaced_instruction(tmp_path: Path, review_hold: str | None) -> tuple[str, dict]:
    products = tmp_path / "_products"
    animas = tmp_path / "animas"
    (animas / "sakura" / "state").mkdir(parents=True)
    _write_product(products, "P-9", code="P-9", review_hold=review_hold)
    surface_pending_reviews(products, animas, older_than_minutes=30, now=_now(), write_pending=False)
    task = [t for t in TaskQueueManager(animas / "sakura").list_tasks() if (t.meta or {}).get("kind") == REVIEW_KIND][0]
    return task.meta["task_desc"]["description"], task.meta


def test_unknown_approval_instruction_is_gated(tmp_path: Path) -> None:
    from core.i18n import t

    description, meta = _surfaced_instruction(tmp_path, None)
    gate = t("review_surfacer.approval_gate", hold="unknown")
    assert gate.strip() and gate.strip() in description
    assert meta["review_hold"] == "unknown"
    criteria = meta["task_desc"]["acceptance_criteria"]
    assert any("unless review_hold: false" in c for c in criteria)


def test_released_instruction_has_no_gate(tmp_path: Path) -> None:
    from core.i18n import t

    description, meta = _surfaced_instruction(tmp_path, "false")
    assert t("review_surfacer.approval_gate", hold="released").strip() not in description
    assert meta["review_hold"] == "released"


def test_hold_placed_during_scan_is_skipped(tmp_path: Path, monkeypatch) -> None:
    import core.reports.pending_review_surfacer as mod

    products = tmp_path / "_products"
    animas = tmp_path / "animas"
    (animas / "sakura" / "state").mkdir(parents=True)
    path = _write_product(products, "P-10", code="P-10")
    original = mod.find_pending_reviews

    def scan_then_hold(*args, **kwargs):
        items = original(*args, **kwargs)
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("confirmed: false", "confirmed: false\nreview_hold: true"), encoding="utf-8")
        return items

    monkeypatch.setattr(mod, "find_pending_reviews", scan_then_hold)
    assert mod.surface_pending_reviews(products, animas, older_than_minutes=30, now=_now(), write_pending=False) == []


# ── re-read state is authoritative (task 993d9c411c89) ─────────


_REREAD_CASES = {
    # label: (frontmatter line replacing "review_hold: false"; None = remove the key)
    "missing": None,
    "empty": "review_hold:",
    "maybe": "review_hold: maybe",
    "true": "review_hold: true",
}


def _surface_with_reread(tmp_path: Path, monkeypatch, replacement: str | None, *, write_pending: bool = True):
    """Scan sees review_hold: false, then the marker changes before enqueue."""
    import core.reports.pending_review_surfacer as mod

    products = tmp_path / "_products"
    animas = tmp_path / "animas"
    (animas / "sakura" / "state").mkdir(parents=True)
    path = _write_product(products, "P-20", code="P-20", review_hold="false")
    original = mod.find_pending_reviews
    scanned: list = []

    def scan_then_change(*args, **kwargs):
        items = original(*args, **kwargs)
        scanned.extend(items)
        text = path.read_text(encoding="utf-8")
        new_line = "" if replacement is None else replacement + "\n"
        path.write_text(text.replace("review_hold: false\n", new_line), encoding="utf-8")
        return items

    monkeypatch.setattr(mod, "find_pending_reviews", scan_then_change)
    surfaced = mod.surface_pending_reviews(
        products, animas, older_than_minutes=30, now=_now(), write_pending=write_pending
    )
    assert [i["review_hold"] for i in scanned] == ["released"]  # precondition: scan-time released
    tasks = [t for t in TaskQueueManager(animas / "sakura").list_tasks() if (t.meta or {}).get("kind") == REVIEW_KIND]
    return surfaced, tasks, animas


def _assert_no_unapproved_completion(text: str) -> None:
    """No unconditional completion step may remain when approval is not recorded."""
    from core.i18n import t

    assert t("review_surfacer.approve_condition_released") not in text
    assert t("review_surfacer.approve_condition_gated") in text
    assert t("review_surfacer.post_condition_gated") in text


_CONFIRMED_PROHIBITION = ("変更しない", "してはいけません", "Do not", "do not", "owner-managed")


def _assert_no_confirmed_change_instruction(texts: list[str]) -> None:
    for text in texts:
        assert not re.search(r"confirmed\s*[:：=]\s*true", text, re.IGNORECASE), text
        for sentence in re.split(r"[。\n]|(?<=\.)\s", text):
            if "confirmed" in sentence.lower():
                assert any(m in sentence for m in _CONFIRMED_PROHIBITION), sentence


@pytest.mark.parametrize("label", ["missing", "empty", "maybe"])
def test_scan_released_then_unknown_on_reread_is_gated(tmp_path: Path, monkeypatch, label: str) -> None:
    from core.i18n import t

    surfaced, tasks, animas = _surface_with_reread(tmp_path, monkeypatch, _REREAD_CASES[label])

    assert len(tasks) == 1
    task = tasks[0]
    desc = task.meta["task_desc"]
    # instruction / meta / surfaced item all follow the re-read state, not the scan
    assert task.meta["review_hold"] == "unknown"
    assert task.meta["review_hold_at_scan"] == "released"
    assert surfaced[0]["review_hold"] == "unknown"
    gate = t("review_surfacer.approval_gate", hold="unknown").strip()
    for text in (task.original_instruction, desc["description"]):
        assert gate in text
        _assert_no_unapproved_completion(text)
    assert desc["description"] == task.original_instruction
    pending = json.loads((animas / "sakura" / "state" / "pending" / f"{task.task_id}.json").read_text(encoding="utf-8"))
    assert pending["description"] == desc["description"]
    _assert_no_confirmed_change_instruction(
        [task.original_instruction, desc["description"], gate, *desc["acceptance_criteria"]]
    )


def test_scan_released_then_held_on_reread_enqueues_nothing(tmp_path: Path, monkeypatch) -> None:
    surfaced, tasks, animas = _surface_with_reread(tmp_path, monkeypatch, _REREAD_CASES["true"])

    assert surfaced == []
    assert tasks == []
    assert not (animas / "sakura" / "state" / "pending").exists()


def test_released_on_reread_keeps_plain_steps_without_confirmed_change(tmp_path: Path) -> None:
    description, meta = _surfaced_instruction(tmp_path, "false")

    assert meta["review_hold"] == "released"
    assert meta["review_hold_at_scan"] == "released"
    from core.i18n import t

    assert t("review_surfacer.approve_condition_released") in description
    assert t("review_surfacer.approve_condition_gated") not in description
    _assert_no_confirmed_change_instruction([description, *meta["task_desc"]["acceptance_criteria"]])


def test_unknown_gate_text_in_english_has_no_confirmed_change_instruction() -> None:
    from core.i18n.strings.misc import STRINGS

    texts = [
        STRINGS[key][lang]
        for key in (
            "review_surfacer.approval_gate",
            "review_surfacer.approve_condition_released",
            "review_surfacer.approve_condition_gated",
            "review_surfacer.post_condition_gated",
            "review_surfacer.confirmed_owner_managed",
        )
        for lang in ("ja", "en")
    ]
    _assert_no_confirmed_change_instruction(texts)


@pytest.mark.parametrize(
    ("old", "new"),
    [("status: レビュー待ち", "status: 完了"), ("confirmed: false", "confirmed: true")],
)
def test_finished_on_reread_is_not_surfaced(tmp_path: Path, monkeypatch, old: str, new: str) -> None:
    import core.reports.pending_review_surfacer as mod

    products = tmp_path / "_products"
    animas = tmp_path / "animas"
    (animas / "sakura" / "state").mkdir(parents=True)
    path = _write_product(products, "P-21", code="P-21")
    original = mod.find_pending_reviews

    def scan_then_finish(*args, **kwargs):
        items = original(*args, **kwargs)
        path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
        return items

    monkeypatch.setattr(mod, "find_pending_reviews", scan_then_finish)
    assert mod.surface_pending_reviews(products, animas, older_than_minutes=30, now=_now(), write_pending=False) == []
    assert TaskQueueManager(animas / "sakura").list_tasks() == []
