from pathlib import Path

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

    write_text(data_json, '{"latest_date": "2026-06-12"}\n')
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

    expected_mean = f"{round(2153.8 / report.TSUBO_TO_SQM, 1):,.1f}"
    expected_median = f"{round(1915.7 / report.TSUBO_TO_SQM, 1):,.1f}"
    expected_trend = f"{round(2180.5 / report.TSUBO_TO_SQM, 1):,.1f}"

    assert "平均平米単価" in markdown
    assert "中央値平米単価" in markdown
    assert "円/㎡" in markdown
    assert expected_mean in markdown
    assert expected_median in markdown
    assert expected_trend in markdown
    assert "2,153.8" not in markdown
    assert "1,915.7" not in markdown
