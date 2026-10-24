from pathlib import Path

from core.reports.property.sale_property_registry import PropertyRegistry


def row(url: str, *, town: str = "今池町1丁目", price: int = 50000000, title: str = "物件A") -> dict:
    return {"url": url, "title": title, "price_jpy": price,
            "raw_text": f"愛知県安城市{town} 名鉄 新安城駅 建:161.82m² 土:183.62m² 1987年3月 3階建/9戸"}


def test_persistent_number_for_cross_portal_duplicates_and_price_changes(tmp_path: Path) -> None:
    path = tmp_path / "registry.sqlite3"
    registry = PropertyRegistry(path)
    a, b = registry.assign([row("https://rakumachi.test/1/show.html"),
                            row("https://kenbiya.test/re_aaa/", town="今池町1", title="別の広告", price=49000000)])
    assert a["property_id"] == b["property_id"] == "PROP-000001"
    registry.close()
    reopened = PropertyRegistry(path)
    try:
        changed = reopened.assign([row("https://rakumachi.test/1/show.html#photo", price=48000000, title="価格改定")])[0]
        reissued = reopened.assign([row("https://rakumachi.test/2/show.html", price=48000000)])[0]
        assert changed["property_id"] == reissued["property_id"] == a["property_id"]
    finally:
        reopened.close()


def test_different_addresses_or_insufficient_evidence_stay_separate(tmp_path: Path) -> None:
    registry = PropertyRegistry(tmp_path / "registry.sqlite3")
    try:
        a, b, c, d, e = registry.assign([
            row("https://example.test/a"), row("https://example.test/b", town="相生町1"),
            {"url": "https://example.test/c", "title": "同じ広告", "price_jpy": 50000000},
            {"url": "https://example.test/d", "title": "同じ広告", "price_jpy": 50000000},
            row("https://example.test/e", town="今池町2丁目"),
        ])
        assert len({r["property_id"] for r in [a, b, c, d, e]}) == 5
    finally:
        registry.close()


def test_multiple_properties_on_a_listing_page_do_not_share_number(tmp_path: Path) -> None:
    registry = PropertyRegistry(tmp_path / "registry.sqlite3")
    try:
        a, b = registry.assign([row("https://example.test/list/", title="A"),
                                row("https://example.test/list/", town="相生町", title="B")])
        assert a["property_id"] != b["property_id"]
    finally:
        registry.close()


def test_daily_report_numbers_tables_and_keeps_original_json(tmp_path: Path, monkeypatch) -> None:
    import json

    from core.reports.property import daily_sale_product_report as daily

    monkeypatch.setattr(daily, "DATA_ROOT", tmp_path)
    report = tmp_path / "daily.md"
    report.write_text("# Daily\n\n| ポータル | 物件 |\n|---|---|\n| A | [物件A](https://example.test/a) |\n", encoding="utf-8")
    result = {"portal_runs": [{"listings": [row("https://example.test/a"), row("https://example.test/b")]}]}
    numbering = daily.ensure_property_numbers(report, result, None, tmp_path)
    assert numbering["listing_count"] == 2 and numbering["property_count"] == 1
    assert "| PROP-000001 | A |" in report.read_text(encoding="utf-8")
    copied = json.loads(Path(numbering["json_path"]).read_text(encoding="utf-8"))
    assert copied[0]["property_id"] == copied[1]["property_id"]
    daily.ensure_property_numbers(report, result, None, tmp_path)
    text = report.read_text(encoding="utf-8")
    assert text.count("## 物件番号台帳") == 1 and text.count("| 物件番号 | ポータル |") == 1
