from __future__ import annotations

import json
from pathlib import Path

from core.execution.base import ToolCallRecord
from core.execution.tool_evidence import ToolEvidence
from core.time_utils import now_jst


def test_started_tool_is_replaced_by_completed_record() -> None:
    evidence = ToolEvidence()
    evidence.started("tool-1", "Read")
    evidence.merge([ToolCallRecord(tool_name="Read", tool_id="tool-1", result_summary="contents")])

    assert evidence.to_dicts() == [
        {
            "tool_name": "Read",
            "tool_id": "tool-1",
            "input_summary": "",
            "result_summary": "contents",
            "is_error": False,
        }
    ]


def test_tool_call_activity_is_recorded_once(tmp_path: Path) -> None:
    evidence = ToolEvidence(tmp_path)
    evidence.record_tool_call(
        "Bash",
        {"command": "printf result"},
        "cmd-1",
        "result",
        extra_meta={"exit_code": 0},
    )
    evidence.record_tool_call("Bash", {"command": "printf result"}, "cmd-1", "result")

    log_file = tmp_path / "activity_log" / f"{now_jst():%Y-%m-%d}.jsonl"
    entries = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    assert [(entry["type"], entry["tool"]) for entry in entries] == [
        ("tool_use", "Bash"),
        ("tool_result", "Bash"),
    ]
    assert entries[0]["content"] == "printf result"
    assert entries[0]["meta"] == {"args": {"command": "printf result"}, "tool_use_id": "cmd-1"}
    assert entries[1]["content"] == "result"
    assert entries[1]["meta"] == {"tool_use_id": "cmd-1", "is_error": False, "exit_code": 0}
