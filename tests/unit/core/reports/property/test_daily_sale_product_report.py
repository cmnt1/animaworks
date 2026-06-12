from pathlib import Path

from core.reports.property import daily_sale_product_report as report


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def test_script_preflight_records_repo_source() -> None:
    provenance = report.script_preflight()

    assert provenance["ok"] is True
    assert provenance["script_path"].endswith(
        "core\\reports\\property\\daily_sale_product_report.py"
    )
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
