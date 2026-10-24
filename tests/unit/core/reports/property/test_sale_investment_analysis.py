from pathlib import Path

import pytest

from core.reports.property import daily_sale_product_report as daily
from core.reports.property.sale_investment_analysis import (
    create_bundle,
    note_frontmatter,
    notification_text,
    render_analysis,
    validate_bundle,
    validate_evidence_analysis,
)


def test_new_listings_have_separate_reports_and_stable_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(daily, "PROPERTY_NOTE_ROOT", tmp_path / "notes")
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    report = tmp_path / "daily.md"
    report.write_text("# Daily\n", encoding="utf-8")
    rows = [
        {"_match_key": "a||1", "url": "https://example.test/a", "title": "A", "price_jpy": 10000000, "gross_yield_percent": 10},
        {"_match_key": "b||1", "url": "https://example.test/b", "title": "B", "gross_yield_percent": None},
    ]
    comparison = {"comparison_available": True, "new_rows": rows, "continued_rows": [{"title": "C"}]}
    bundle = daily.ensure_investment_analysis(report, comparison, "2026-10-25", source, daily.sha256_file(source))
    assert bundle["count"] == 2 and validate_bundle(bundle)
    assert validate_evidence_analysis({"comparison": comparison, "investment_analysis": bundle}) == bundle
    assert "2物件" in notification_text(bundle) and bundle["index_path"] in notification_text(bundle)
    text = Path(bundle["reports"][0]["path"]).read_text(encoding="utf-8")
    assert "追加調査候補" in text and "675,000円" in text  # 1m revenue * .9 * .75
    assert "判断保留" in Path(bundle["reports"][1]["path"]).read_text(encoding="utf-8")
    again = daily.ensure_investment_analysis(report, comparison, "2026-10-25", source, daily.sha256_file(source))
    assert again == bundle
    assert report.read_text(encoding="utf-8").count("## 新規物件の投資可否分析") == 1
    Path(bundle["reports"][0]["path"]).write_text("tampered", encoding="utf-8")
    assert not validate_bundle(bundle)
    with pytest.raises(RuntimeError, match="SHA-256"):
        validate_evidence_analysis({"comparison": comparison, "investment_analysis": bundle})


@pytest.mark.parametrize("comparison,status", [
    (None, "comparison_unavailable"),
    ({"comparison_available": True, "new_rows": []}, "no_new_listings"),
])
def test_no_report_without_new_listings(tmp_path: Path, comparison: dict | None, status: str) -> None:
    bundle = create_bundle(comparison, "2026-10-25", tmp_path, tmp_path / "source.json", "abc")
    assert bundle["status"] == status and bundle["count"] == 0 and validate_bundle(bundle)
    assert not (tmp_path / "investment-analysis").exists()


@pytest.mark.parametrize("price,yield_", [(None, 10), (100, float("nan")), (-1, 10), (100, 0)])
def test_missing_numbers_do_not_imply_investable(price: object, yield_: object) -> None:
    text = render_analysis({"price_jpy": price, "gross_yield_percent": yield_}, "2026-10-25", Path("source.json"), "abc")
    assert "判断保留" in text and "算定不可" in text and "| 基本 |" not in text


def test_low_yield_keeps_analysis_even_when_screen_fails() -> None:
    text = render_analysis({"price_jpy": 10000000, "gross_yield_percent": 5}, "2026-10-25", Path("source.json"), "abc")
    assert "一次基準では見送り" in text and "| 基本 |" in text


def test_incomplete_analysis_blocks_review(tmp_path: Path) -> None:
    bundle = {"status": "no_new_listings", "count": 0, "reports": []}
    with pytest.raises(RuntimeError, match="incomplete"):
        validate_evidence_analysis({"comparison": {"comparison_available": True, "new_rows": [{}]}, "investment_analysis": bundle})
    assert validate_evidence_analysis({}) == {}  # Historical review evidence remains readable.


def test_existing_daily_report_backfills_analysis_without_rescraping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    product = tmp_path / "daily.md"
    product.write_text("---\nstatus: 完了\nconfirmed: true\n---\n# Daily\n", encoding="utf-8")
    evidence_path = tmp_path / "daily-sale-report-draft-20261025.json"
    saved = {
        "status": "done", "data_json_copy_path": str(source), "source_json_sha256": daily.sha256_file(source),
        "read_after_write_checks": {"report_exists": True},
        "comparison": {"comparison_available": True, "new_rows": [{"url": "https://example.test/new", "title": "New"}]},
    }
    evidence_path.write_text(json.dumps(saved), encoding="utf-8")
    monkeypatch.setattr(daily, "find_existing", lambda date: product)
    monkeypatch.setattr(daily, "CATEGORY_DIR", tmp_path)
    monkeypatch.setattr(daily, "DATA_ROOT", tmp_path / "history")
    monkeypatch.setattr(daily, "PROPERTY_NOTE_ROOT", tmp_path / "notes")
    monkeypatch.setattr(daily, "REPORT_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(daily, "run_scan", lambda **kwargs: pytest.fail("must not rescrape"))
    assert daily.main(["--report-date", "2026-10-25", "--task-results-dir", str(tmp_path)]) == 0
    updated = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert updated["investment_analysis"]["count"] == 1 and validate_bundle(updated["investment_analysis"])
    assert daily.read_frontmatter(product) == {"status": "完了", "confirmed": "true"}


def test_duplicate_new_listings_share_one_numbered_analysis(tmp_path: Path) -> None:
    rows = [
        {"property_id": "PROP-000001", "url": "https://example.test/a", "price_jpy": 50000000, "gross_yield_percent": 9.5},
        {"property_id": "PROP-000001", "url": "https://example.test/b", "price_jpy": 49000000, "gross_yield_percent": 9.6},
    ]
    comparison = {"comparison_available": True, "new_rows": rows}
    bundle = create_bundle(comparison, "2026-10-25", tmp_path, tmp_path / "source.json", "abc")
    assert bundle["count"] == 1 and bundle["listing_count"] == 2
    assert validate_evidence_analysis({"comparison": comparison, "investment_analysis": bundle}) == bundle
    text = Path(bundle["reports"][0]["path"]).read_text(encoding="utf-8")
    assert "PROP-000001" in text and "https://example.test/b" in text and "49000000" in text


def test_base_metadata_uses_new_tag_and_only_confirmed_property_names() -> None:
    import yaml

    def fields(row: dict) -> dict:
        return yaml.safe_load(note_frontmatter(row, "2026-10-25").split("---")[1])

    unknown = fields({"property_id": "PROP-000023", "title": "駅徒歩7分 利回り9.5%"})
    assert unknown["タグ"] == ["新規"] and unknown["物件"] is None
    assert unknown["物件番号"] == "PROP-000023"
    assert fields({"raw_text": "・物件名：ハイツジュネス／1棟アパート"})["物件"] == "ハイツジュネス"
    assert fields({"title": "キャッスルパーク/安城市/一棟アパート"})["物件"] == "キャッスルパーク"
