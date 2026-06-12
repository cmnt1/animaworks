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
