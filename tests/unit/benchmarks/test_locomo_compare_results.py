from __future__ import annotations

import json
from pathlib import Path

from benchmarks.locomo.compare_results import compare_result_files, main, render_markdown


def _write_payload(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_compare_results_reports_cat5_excluded_delta_and_blanks(tmp_path: Path) -> None:
    before = _write_payload(
        tmp_path / "before.json",
        {
            "summary": {
                "overall_f1": 0.5,
                "overall_judge": None,
                "by_category": {
                    "multi_hop": {"f1": 0.5, "judge": None, "count": 1},
                    "adversarial": {"f1": 1.0, "judge": None, "count": 1},
                },
            },
            "results": [
                {
                    "sample_id": "conv-1",
                    "question_index": 0,
                    "category": 1,
                    "question": "What did Caroline research?",
                    "reference": "adoption",
                    "prediction": "adoption",
                    "f1": 0.5,
                    "judge_score": None,
                },
                {
                    "sample_id": "conv-1",
                    "question_index": 1,
                    "category": 5,
                    "question": "Unanswerable?",
                    "reference": "No information available.",
                    "prediction": "No information available.",
                    "f1": 1.0,
                    "judge_score": None,
                },
            ],
        },
    )
    after = _write_payload(
        tmp_path / "after.json",
        {
            "summary": {
                "overall_f1": 0.25,
                "overall_judge": None,
                "by_category": {
                    "multi_hop": {"f1": 0.0, "judge": None, "count": 1},
                    "adversarial": {"f1": 1.0, "judge": None, "count": 1},
                },
            },
            "results": [
                {
                    "sample_id": "conv-1",
                    "question_index": 0,
                    "category": 1,
                    "question": "What did Caroline research?",
                    "reference": "adoption",
                    "prediction": "",
                    "f1": 0.0,
                    "judge_score": None,
                },
                {
                    "sample_id": "conv-1",
                    "question_index": 1,
                    "category": 5,
                    "question": "Unanswerable?",
                    "reference": "No information available.",
                    "prediction": "No information available.",
                    "f1": 1.0,
                    "judge_score": None,
                },
            ],
        },
    )

    report = compare_result_files(before, after)

    assert report["deltas"]["overall_f1"] == -0.25
    assert report["deltas"]["cat5_excluded_overall_f1"] == -0.5
    assert report["deltas"]["blank_predictions"] == 1
    assert report["questions"]["regression_count"] == 1
    assert report["questions"]["worst_regressions"][0]["after_blank"] is True


def test_compare_results_recomputes_missing_summary_and_writes_outputs(tmp_path: Path) -> None:
    before = _write_payload(
        tmp_path / "before.json",
        {
            "results": [
                {
                    "sample_id": "conv-1",
                    "question_index": 0,
                    "category": 4,
                    "question": "Which book?",
                    "reference": "Becoming Nicole",
                    "prediction": "Becoming Nicole",
                    "f1": 1.0,
                    "judge_score": None,
                }
            ]
        },
    )
    after = _write_payload(
        tmp_path / "after.json",
        {
            "results": [
                {
                    "sample_id": "conv-1",
                    "question_index": 0,
                    "category": 4,
                    "question": "Which book?",
                    "reference": "Becoming Nicole",
                    "prediction": "Becoming Nicole",
                    "f1": 1.0,
                    "judge_score": None,
                }
            ]
        },
    )
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"

    assert main([str(before), str(after), "--output", str(out_json), "--markdown", str(out_md)]) == 0

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["before"]["missing_summary"] is True
    assert payload["before"]["overall_f1"] == 1.0
    markdown = out_md.read_text(encoding="utf-8")
    assert "Cat5-excluded F1" in markdown
    assert "summary was missing" in markdown


def test_render_markdown_includes_best_and_worst_sections(tmp_path: Path) -> None:
    before = _write_payload(
        tmp_path / "before.json",
        {
            "results": [
                {
                    "sample_id": "conv-1",
                    "question_index": 0,
                    "category": 1,
                    "question": "Q",
                    "reference": "A",
                    "prediction": "bad",
                    "f1": 0.0,
                    "judge_score": None,
                }
            ]
        },
    )
    after = _write_payload(
        tmp_path / "after.json",
        {
            "results": [
                {
                    "sample_id": "conv-1",
                    "question_index": 0,
                    "category": 1,
                    "question": "Q",
                    "reference": "A",
                    "prediction": "A",
                    "f1": 1.0,
                    "judge_score": None,
                }
            ]
        },
    )

    markdown = render_markdown(compare_result_files(before, after))

    assert "Best Improvements" in markdown
    assert "+100.00pt" in markdown
