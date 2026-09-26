import json
from pathlib import Path
from types import SimpleNamespace

from core.reports.property import anjo_1k_product_draft as report


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def test_script_preflight_records_repo_source() -> None:
    provenance = report.script_preflight()
    script_path = provenance["script_path"].replace("\\", "/")

    assert provenance["ok"] is True
    assert script_path.endswith("core/reports/property/anjo_1k_product_draft.py")
    assert provenance["script_size_bytes"] > 0
    assert len(provenance["script_sha256"]) == 64
    assert provenance["checks"]["py_compile_ok"] is True


def test_write_evidence_requires_product_and_data_copy(tmp_path: Path) -> None:
    report_path = tmp_path / "products" / "Property" / "P-00001_anjo-1k-20260612.md"
    data_json = tmp_path / "data" / "P-00001_anjo-1k-20260612_data.json"
    source_json = tmp_path / "suumo" / "anjo_1k_market_metrics_20260612.json"

    write_text(
        data_json,
        json.dumps(
            {
                "latest_date": "2026-06-12",
                "minimini_url_snapshot": {
                    "fetch_status": "success",
                    "listing_count": 1,
                    "listings": {
                        "room_count": 1,
                        "rooms": [{"detail_url": "https://example.com/1"}],
                        "parking_enriched": {"fetched": 1, "failed": 0, "cached": 0, "stale": 0},
                    },
                },
            }
        )
        + "\n",
    )
    write_text(source_json, data_json.read_text(encoding="utf-8"))
    digest = report.sha256_file(source_json)
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
        "P-00001",
        "2026-06-12",
        report_path,
        data_json,
        source_json,
        digest,
        task_results_dir=tmp_path / "task_results",
        script_provenance=provenance,
    )

    assert evidence["status"] == "done"
    assert Path(evidence["evidence_path"]).exists()
    assert evidence["script_path"] == provenance["script_path"]
    assert evidence["script_sha256"] == provenance["script_sha256"]
    assert evidence["script_py_compile_ok"] is True
    assert evidence["read_after_write_checks"]["script_preflight_ok"] is True
    assert evidence["read_after_write_checks"]["minimini_available"] is True
    assert evidence["task_closure"]["can_submit"] is True
    assert evidence["task_closure"]["acceptance_checks"]


def test_minimini_gate_reports_failed_or_incomplete_snapshot() -> None:
    gate = report.validate_minimini_snapshot(
        {
            "minimini_url_snapshot": {
                "fetch_status": "failed",
                "listing_count": None,
                "error": "No listing-count pattern matched",
                "listings": {"room_count": 0, "rooms": []},
            }
        }
    )

    assert gate["ok"] is False
    assert "fetch_status=failed" in gate["reasons"]
    assert "listing_count_missing_or_invalid" in gate["reasons"]


def test_minimini_gate_accepts_capture_with_skipped_details() -> None:
    def snapshot(enriched: dict) -> dict:
        return {
            "minimini_url_snapshot": {
                "fetch_status": "success",
                "listing_count": 3,
                "listings": {
                    "room_count": 3,
                    "rooms": [{}, {}, {}],
                    "parking_enriched": enriched,
                },
            }
        }

    gate = report.validate_minimini_snapshot(
        snapshot({"fetched": 0, "failed": 0, "cached": 2, "stale": 0, "skipped": 1})
    )
    assert gate["ok"] is True
    assert gate["detail_skipped"] == 1

    gate = report.validate_minimini_snapshot(snapshot({"fetched": 0, "failed": 0, "cached": 2, "stale": 0}))
    assert "detail_coverage_mismatch=0+2+0/3" in gate["reasons"]


def test_write_evidence_allows_minimini_unavailable_with_note(tmp_path: Path) -> None:
    report_path = tmp_path / "products" / "Property" / "P-00002_anjo-1k-20260613.md"
    data_json = tmp_path / "data" / "P-00002_anjo-1k-20260613_data.json"
    source_json = tmp_path / "suumo" / "anjo_1k_market_metrics_20260613.json"
    source_data = {
        "latest_date": "2026-06-13",
        "minimini_url_snapshot": {
            "fetch_status": "failed",
            "listing_count": None,
            "http_status": 200,
            "error": "Google reCAPTCHA challenge page returned instead of listing HTML",
        },
    }
    write_text(data_json, json.dumps(source_data) + "\n")
    write_text(source_json, data_json.read_text(encoding="utf-8"))
    digest = report.sha256_file(source_json)
    write_text(
        report_path,
        f"""---
type: product
code: P-00002
category: Property
status: レビュー待ち
task_code: {report.TASK_CODE}
report_date: 2026-06-13
source_json_sha256: {digest}
assignee: hikaru
reviewer: sakura
---
# Report

> [!warning] minimini掲載一覧は取得未完了（注記付き完了可）
""",
    )

    evidence = report.write_evidence(
        "P-00002",
        "2026-06-13",
        report_path,
        data_json,
        source_json,
        digest,
        task_results_dir=tmp_path / "task_results",
        script_provenance=report.script_preflight(),
    )

    assert evidence["status"] == "done"
    assert evidence["read_after_write_checks"]["minimini_available"] is False
    assert all(evidence["blocking_read_after_write_checks"].values())
    assert evidence["advisory_checks"] == {"minimini_available": False}
    assert evidence["completion_policy"]["minimini_required"] is False
    assert evidence["task_closure"]["can_submit"] is True
    assert evidence["task_closure"]["remaining_blockers"] == []
    assert evidence["warnings"][0]["code"] == "minimini_unavailable"


def test_minimini_unavailable_notification_is_sent_once(tmp_path: Path, monkeypatch) -> None:
    fake_tool = tmp_path / "animaworks-tool.exe"
    fake_tool.write_text("", encoding="utf-8")
    monkeypatch.setattr(report, "ANIMAWORKS_TOOL", fake_tool)
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="Sent (id: 123456789)", stderr="")

    monkeypatch.setattr(report.subprocess, "run", fake_run)
    kwargs = {
        "code": "P-00001",
        "report_date": "2026-06-12",
        "report_path": tmp_path / "report.md",
        "source_json": tmp_path / "source.json",
        "gate": {
            "ok": False,
            "fetch_status": "failed",
            "listing_count": None,
            "error": "recaptcha challenge",
            "reasons": ["fetch_status=failed"],
        },
        "task_results_dir": tmp_path / "task_results",
    }

    first = report.send_minimini_unavailable_notification(**kwargs)
    second = report.send_minimini_unavailable_notification(**kwargs)

    assert first["status"] == "ok"
    assert first["message_id"] == "123456789"
    assert second["status"] == "verified_existing"
    assert len(calls) == 1
    assert any("取得未完了" in part and "注記付き完了可" in part for part in calls[0])


def test_get_prev_minimini_count_ignores_untrusted_patterns(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(report, "PRODUCT_DATA_ROOT", tmp_path)
    prev_dir = tmp_path / "2026" / "06" / "16"
    write_text(
        prev_dir / "P-00001_anjo-1k-20260616_data.json",
        """{
  "minimini_url_snapshot": {
    "fetch_status": "success",
    "listing_count": 30,
    "pattern_used": "([0-9][0-9,]*)件"
  }
}
""",
    )

    assert report.get_prev_minimini_count("2026-06-16") is None


def test_get_prev_minimini_count_accepts_strict_kensu_pattern(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(report, "PRODUCT_DATA_ROOT", tmp_path)
    prev_dir = tmp_path / "2026" / "06" / "16"
    write_text(
        prev_dir / "P-00001_anjo-1k-20260616_data.json",
        """{
  "minimini_url_snapshot": {
    "fetch_status": "success",
    "listing_count": 19,
    "pattern_used": "p.kensu strong count"
  }
}
""",
    )

    assert report.get_prev_minimini_count("2026-06-16") == 19


def test_build_minimini_listing_section_includes_single_built_column() -> None:
    section = report.build_minimini_listing_section(
        {
            "listings": {
                "sort": "新着順",
                "building_count": 2,
                "room_count": 2,
                "own_room_count": 1,
                "own_term": "太陽",
                "buildings": [
                    {"building_order": 1, "built": "築7年 /"},
                    {"order": 2, "built": "築12年"},
                ],
                "rooms": [
                    {
                        "building_order": 1,
                        "is_own": True,
                        "bname": "太陽ハイツ",
                        "address": "愛知県安城市",
                        "station": "安城駅 徒歩7分",
                        "floor": "2階",
                        "rent": "55,000円",
                        "mgmt_fee": "3,000円",
                        "deposit": "なし",
                        "key_money": "なし",
                        "layout": "1K",
                        "area": "25.0㎡",
                        "parking": "5,000円",
                        "move_in": "即入居可",
                        "detail_url": "https://example.com/1",
                    },
                    {
                        "building_order": 2,
                        "bname": "サンプルコート",
                        "address": "愛知県安城市",
                        "station": "南安城駅 徒歩5分",
                        "floor": "1階",
                        "rent": "50,000円",
                        "mgmt_fee": "2,000円",
                        "deposit": "1ヶ月",
                        "key_money": "なし",
                        "layout": "1K",
                        "area": "23.0㎡",
                        "parking": "近隣",
                        "move_in": "相談",
                    },
                ],
            }
        }
    )

    header = next(line for line in section.splitlines() if line.startswith("| 新着順 "))
    separator = next(line for line in section.splitlines() if line.startswith("|---:"))
    rows = [line for line in section.splitlines() if line.startswith("| 1 |") or line.startswith("| 2 |")]

    assert header.count("築年") == 1
    assert "築7年 /" not in section
    assert "築7年" in rows[0]
    assert "築12年" in rows[1]
    assert "**【自社】太陽ハイツ**" in rows[0]
    assert header.count("|") == 16
    assert separator.count("|") == 16
    assert all(row.count("|") == 16 for row in rows)


def test_render_markdown_switches_to_sqm_from_20260626() -> None:
    assert report.report_uses_sqm_unit_price("2026-06-26") is True
    assert report.report_uses_sqm_unit_price("2026-06-25") is False

    data = {
        "latest_date": "2026-06-26",
        "prev_date": "2026-06-25",
        "meta": {
            "latest_date_in_db": "2026-06-26",
            "extraction_time": "2026-06-26T00:00:00",
            "rent_column_used": "Base_Rent / Ocu_Area",
            "data_range": {"min_date": "2026-06-20", "max_date": "2026-06-26"},
        },
        "listing_count": {"latest": 120, "prev": 118, "change": 2},
        "rent": {
            "latest": {"mean": 65000, "median": 62000},
            "prev": {"mean": 64000, "median": 61000},
            "change_mean": 1000,
            "change_median": 1000,
        },
        "unit_price": {
            "latest": {"mean": 2153.8, "median": 1915.7},
            "prev": {"mean": 2100.0, "median": 1880.0},
            "change_mean": 53.8,
            "change_median": 35.7,
        },
        "vacancy_proxy": {"median_obs_days": 12, "pct_listings_7plus_days": 25.0},
        "trend_7d": [
            {
                "date": "2026-06-20",
                "listing_count": 80,
                "avg_rent": 60000,
                "median_rent": 59000,
                "avg_unit_price": 2153.8,
            },
            {
                "date": "2026-06-21",
                "listing_count": 82,
                "avg_rent": 60500,
                "median_rent": 59500,
                "avg_unit_price": 2200.0,
            },
            {
                "date": "2026-06-22",
                "listing_count": 84,
                "avg_rent": 61000,
                "median_rent": 60000,
                "avg_unit_price": 2180.5,
            },
        ],
        "minimini_url_snapshot": {
            "listing_count": 12,
            "fetched_at": "2026-06-26T00:00:00+09:00",
            "method": "p.kensu strong count",
            "url": "https://example.com",
            "http_status": 200,
        },
    }

    markdown = report.render_markdown(
        159,
        "P-00159",
        data,
        Path(r"E:\dummy\source.json"),
        Path(r"E:\dummy\copy.json"),
        "0" * 64,
        "2026-06-26T00:00:00+09:00",
        "2026-06-26T00:00:00+09:00",
        "false",
        prev_minimini_count=25,
    )

    # Source unit_price (Base_Rent / Ocu_Area) is already per-㎡, so the switch
    # only relabels 坪→㎡; the numeric values must stay unchanged.
    assert "平均平米単価" in markdown
    assert "中央値平米単価" in markdown
    assert "円/㎡" in markdown
    assert "平均坪単価" not in markdown
    assert "円/坪" not in markdown
    assert "2,153.8" in markdown
    assert "1,915.7" in markdown
    assert "2,180.5" in markdown


def _mm_room(url: str, **extra) -> dict:
    return {"detail_url": f"https://minimini.jp/detail/{url}/", "bname": f"建物{url}", "rent": "5.0万円", **extra}


def _mm_snapshot(*urls: str) -> dict:
    return {"fetch_status": "success", "listings": {"rooms": [_mm_room(u) for u in urls]}}


def test_minimini_diff_tracks_new_continued_deleted_and_listing_days() -> None:
    history = [
        ("2026-09-01", [_mm_room("a"), _mm_room("b")]),
        ("2026-09-02", [_mm_room("a"), _mm_room("b"), _mm_room("c")]),
        # 09-03..09-04 not observed (no capture): normal gap, runs continue.
        ("2026-09-05", [_mm_room("a"), _mm_room("c"), _mm_room("d")]),
    ]
    diff = report.build_minimini_diff("2026-09-08", _mm_snapshot("a", "d", "e"), history)

    assert diff["available"] is True
    assert diff["previous_date"] == "2026-09-05"
    new = {r["detail_url"]: r for r in diff["new_rows"]}
    cont = {r["detail_url"]: r for r in diff["continued_rows"]}
    gone = {r["detail_url"]: r for r in diff["deleted_rows"]}
    url = "https://minimini.jp/detail/{}/".format

    assert set(new) == {url("e")} and new[url("e")]["listing_day"] == 1
    assert cont[url("a")]["listing_day"] == 8 and cont[url("a")]["start_uncertain"] is True  # first data day
    assert cont[url("d")]["listing_day"] == 4 and cont[url("d")]["start_uncertain"] is False
    assert set(gone) == {url("c")}
    assert gone[url("c")]["listing_start"] == "2026-09-02"
    assert gone[url("c")]["last_seen"] == "2026-09-05"
    assert gone[url("c")]["listing_days"] == 4


def test_minimini_diff_relisting_restarts_and_long_gap_is_uncertain() -> None:
    history = [
        ("2026-08-01", [_mm_room("x")]),
        ("2026-08-02", [_mm_room("y")]),  # x withdrawn
        ("2026-08-03", [_mm_room("x"), _mm_room("y")]),  # x relisted
    ]
    diff = report.build_minimini_diff("2026-09-26", _mm_snapshot("x", "z"), history)
    cont = {r["detail_url"]: r for r in diff["continued_rows"]}
    new = {r["detail_url"]: r for r in diff["new_rows"]}
    assert cont["https://minimini.jp/detail/x/"]["listing_start"] == "2026-08-03"
    assert new["https://minimini.jp/detail/z/"]["start_uncertain"] is True  # 54-day gap
    section = report.build_minimini_diff_section(diff)
    assert "前回取得から54日空いている" in section
    assert "1日目以上" in section
    assert "| 該当なし |" not in section.split("#### 削除")[0]


def test_minimini_diff_unavailable_without_current_or_history() -> None:
    assert report.build_minimini_diff("2026-09-26", {"fetch_status": "failed"}, [])["available"] is False
    diff = report.build_minimini_diff("2026-09-26", _mm_snapshot("a"), [])
    assert diff["available"] is False
    assert "比較できる過去" in report.build_minimini_diff_section(diff)


def test_load_minimini_history_skips_failed_and_future_days(tmp_path: Path) -> None:
    def put(ymd: str, snapshot: dict) -> None:
        write_text(
            tmp_path / ymd[:4] / ymd[4:6] / ymd[6:] / f"anjo_1k_market_metrics_{ymd}.json",
            json.dumps({"minimini_url_snapshot": snapshot}),
        )

    put("20260901", _mm_snapshot("a"))
    put("20260902", {"fetch_status": "failed"})
    put("20260926", _mm_snapshot("b"))
    history = report.load_minimini_history("2026-09-26", root=tmp_path)
    assert [date for date, _ in history] == ["2026-09-01"]
