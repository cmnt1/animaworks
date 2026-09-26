from pathlib import Path

from core.reports.property import daily_sale_product_report as report


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def test_script_preflight_records_repo_source() -> None:
    provenance = report.script_preflight()
    script_path = provenance["script_path"].replace("\\", "/")

    assert provenance["ok"] is True
    assert script_path.endswith("core/reports/property/daily_sale_product_report.py")
    assert provenance["script_size_bytes"] > 0
    assert len(provenance["script_sha256"]) == 64
    assert provenance["checks"]["py_compile_ok"] is True


def test_write_evidence_requires_outputs_and_records_provenance(tmp_path: Path) -> None:
    report_path = tmp_path / "products" / "Property" / "P-00001_daily-sale-info-20260612.md"
    data_json = tmp_path / "data" / "P-00001_daily-sale-info-20260612.json"
    data_md = tmp_path / "data" / "P-00001_daily-sale-info-20260612.md"
    data_csv = tmp_path / "data" / "P-00001_daily-sale-info-20260612.csv"
    source_json = tmp_path / "reports" / "scan.json"
    source_md = tmp_path / "reports" / "scan.md"
    source_csv = tmp_path / "reports" / "scan.csv"

    write_text(data_json, '{"ok": true}\n')
    digest = report.sha256_file(data_json)
    write_text(source_json, '{"ok": true}\n')
    write_text(data_md, "# scan\n")
    write_text(source_md, "# scan\n")
    write_text(data_csv, "url,title\nhttps://example.test/a,A\n")
    write_text(source_csv, "url,title\nhttps://example.test/a,A\n")
    write_text(
        report_path,
        f"""---
type: product
code: P-00001
category: Property
status: レビュー待ち
task_code: {report.TASK_CODE}
report_date: 2026-06-12
source_json_sha256: {digest}
assignee: hikaru
reviewer: sakura
---
# Report
""",
    )
    provenance = report.script_preflight()

    evidence = report.write_evidence(
        code="P-00001",
        report_date="2026-06-12",
        report_path=report_path,
        data_json_copy=data_json,
        data_md_copy=data_md,
        data_csv_copy=data_csv,
        scraper_json=source_json,
        scraper_md=source_md,
        scraper_csv=source_csv,
        digest=digest,
        result={
            "portal_runs": [
                {
                    "listing_count": 1,
                    "listings": [{"review_status": "passes_min_gross_yield"}],
                }
            ]
        },
        comparison=None,
        task_results_dir=tmp_path / "task_results",
        script_provenance=provenance,
    )

    assert evidence["status"] == "done"
    assert Path(evidence["evidence_path"]).exists()
    assert evidence["script_path"] == provenance["script_path"]
    assert evidence["script_sha256"] == provenance["script_sha256"]
    assert evidence["script_py_compile_ok"] is True
    assert evidence["read_after_write_checks"]["script_preflight_ok"] is True


CSV_HEAD = "portal_label,title,property_type,price_text,price_jpy,gross_yield_percent,review_status,url\n"


def _put_day(root: Path, ymd: str, rows: list[tuple[str, str]], fetched: list[str]) -> Path:
    import json

    day = root / ymd[:4] / ymd[4:6] / ymd[6:]
    csv_path = day / f"P-{ymd[4:]}_{report.SLUG_PREFIX}-{ymd}.csv"
    body = "".join(f"{portal},{key},,,,,,https://example.test/{key}\n" for portal, key in rows)
    write_text(csv_path, CSV_HEAD + body)
    runs = [{"portal_label": p, "fetched": True} for p in fetched]
    write_text(csv_path.with_suffix(".json"), json.dumps({"portal_runs": runs}))
    return csv_path


def _classify(tmp_path: Path, today: str, cur: Path, fetched: set[str]) -> dict:
    history = report.load_sale_history(today, root=tmp_path)
    return report.build_url_diff_report(cur, today, history=history, fetched_portals=fetched)


def _titles(rows: list[dict]) -> dict:
    return {r["title"]: r for r in rows}


def test_sale_diff_adds_listing_days_and_holds_unfetched_portals(tmp_path: Path) -> None:
    _put_day(tmp_path, "20260920", [("楽待", "a"), ("健美家", "k")], ["楽待", "健美家"])
    _put_day(tmp_path, "20260921", [("楽待", "a"), ("楽待", "b"), ("健美家", "k")], ["楽待", "健美家"])
    # 09-22: 健美家 fetch failed -> its listing is neither deleted nor restarted
    _put_day(tmp_path, "20260922", [("楽待", "a"), ("楽待", "b")], ["楽待"])
    _put_day(tmp_path, "20260923", [("楽待", "a"), ("楽待", "b"), ("健美家", "k")], ["楽待", "健美家"])
    cur = _put_day(tmp_path, "20260924", [("楽待", "a"), ("楽待", "c")], ["楽待"])

    diff = _classify(tmp_path, "2026-09-24", cur, {"楽待"})
    assert diff["previous_date"] == "2026-09-23"
    new, cont = _titles(diff["new_rows"]), _titles(diff["continued_rows"])
    gone, held = _titles(diff["deleted_rows"]), _titles(diff["unconfirmed_rows"])
    assert new["c"]["listing_day"] == 1 and new["c"]["start_uncertain"] is False
    assert cont["a"]["listing_day"] == 5 and cont["a"]["start_uncertain"] is True  # first data day
    assert set(gone) == {"b"} and diff["deleted_count"] == 1
    assert gone["b"]["listing_start"] == "2026-09-21" and gone["b"]["last_seen"] == "2026-09-23"
    assert gone["b"]["listing_days"] == 3
    assert set(held) == {"k"} and held["k"]["listing_start"] == "2026-09-20"

    md = report.diff_rows_to_markdown(diff["deleted_rows"], days="withdrawn")
    assert "| 掲載開始 | 最終確認 | 掲載日数 |" in md and "| 3日 |" in md
    assert "| 5日目以上 |" in report.diff_rows_to_markdown(diff["continued_rows"], days="listed")
    assert "| 該当なし | - | - | - | - | - | - | - |" in report.diff_rows_to_markdown([], days="listed")


def test_sale_diff_uses_last_observation_not_yesterdays_file(tmp_path: Path) -> None:
    _put_day(tmp_path, "20260920", [("楽待", "a"), ("健美家", "k"), ("健美家", "m")], ["楽待", "健美家"])
    # 09-21: 健美家 failed (k, m kept open); 09-22: no files at all
    _put_day(tmp_path, "20260921", [("楽待", "a")], ["楽待"])
    cur = _put_day(tmp_path, "20260923", [("楽待", "a"), ("健美家", "k")], ["楽待", "健美家"])

    diff = _classify(tmp_path, "2026-09-23", cur, {"楽待", "健美家"})
    assert diff["comparison_available"] is True  # yesterday's CSV is missing
    assert _titles(diff["new_rows"]) == {}  # k is continued, not new after its portal recovered
    assert _titles(diff["continued_rows"])["k"]["listing_start"] == "2026-09-20"
    assert set(_titles(diff["deleted_rows"])) == {"m"}  # withdrawn while 健美家 was failing


def test_sale_diff_without_history_is_unavailable(tmp_path: Path) -> None:
    cur = _put_day(tmp_path, "20260924", [("楽待", "b")], ["楽待"])
    diff = _classify(tmp_path, "2026-09-24", cur, {"楽待"})
    assert diff["comparison_available"] is False and diff["current_count"] == 1


def _put_rows(root: Path, ymd: str, rows: list[tuple[str, str, str, int, float]]) -> Path:
    """rows: (portal, url_id, title, price_jpy, gross_yield_percent)."""
    import json

    day = root / ymd[:4] / ymd[4:6] / ymd[6:]
    csv_path = day / f"P-{ymd[4:]}_{report.SLUG_PREFIX}-{ymd}.csv"
    body = "".join(f"{p},{t},,,{price},{y},,https://example.test/{u}\n" for p, u, t, price, y in rows)
    write_text(csv_path, CSV_HEAD + body)
    portals = sorted({p for p, *_ in rows})
    write_text(csv_path.with_suffix(".json"), json.dumps({"portal_runs": [{"portal_label": p, "fetched": True} for p in portals]}))
    return csv_path


def test_relisting_under_new_id_continues_the_same_listing(tmp_path: Path) -> None:
    old = ("楽待", "a1", "①結論 利回り11.67％ 3枚 価格", 60000000, 11.67)
    other = ("楽待", "b", "別物件", 30000000, 8.0)
    _put_rows(tmp_path, "20260920", [old, other])
    _put_rows(tmp_path, "20260921", [old, other])
    cur = _put_rows(tmp_path, "20260922", [("楽待", "a2", "①結論 利回り11.67％ 5枚 価格 New", 60000000, 11.67), other])

    diff = _classify(tmp_path, "2026-09-22", cur, {"楽待"})
    assert diff["new_rows"] == [] and diff["deleted_rows"] == []
    relisted = next(r for r in diff["continued_rows"] if r["url"].endswith("/a2"))
    assert relisted["listing_start"] == "2026-09-20" and relisted["listing_day"] == 3
    assert relisted["relisted_today"] is True and diff["relisted_count"] == 1
    assert relisted["relisted_from"] == ["https://example.test/a1||1"]
    md = report.diff_rows_to_markdown(diff["continued_rows"], days="listed")
    assert "※ID変更（[旧URL](https://example.test/a1)）" in md


def test_relisting_requires_same_price_and_recent_withdrawal(tmp_path: Path) -> None:
    title = "①結論 利回り11.67％ 3枚 価格"
    _put_rows(tmp_path, "20260901", [("楽待", "a1", title, 60000000, 11.67), ("楽待", "z", "他", 1, 1.0)])
    _put_rows(tmp_path, "20260910", [("楽待", "z", "他", 1, 1.0)])  # a1 withdrawn 09-10
    # 09-20: same title again, but last seen 09-01 is far beyond the gap -> a new listing
    cur = _put_rows(tmp_path, "20260920", [("楽待", "a2", title, 60000000, 11.67), ("楽待", "z", "他", 1, 1.0)])
    diff = _classify(tmp_path, "2026-09-20", cur, {"楽待"})
    assert [r["url"] for r in diff["new_rows"]] == ["https://example.test/a2"]

    _put_rows(tmp_path, "20260921", [("楽待", "a2", title, 60000000, 11.67), ("楽待", "z", "他", 1, 1.0)])
    cur = _put_rows(tmp_path, "20260922", [("楽待", "a3", title, 55000000, 11.67), ("楽待", "z", "他", 1, 1.0)])
    diff = _classify(tmp_path, "2026-09-22", cur, {"楽待"})  # price changed -> not the same listing
    assert [r["url"] for r in diff["new_rows"]] == ["https://example.test/a3"]
    assert [r["url"] for r in diff["deleted_rows"]] == ["https://example.test/a2"]
