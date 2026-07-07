from core.task_closure import (
    build_task_closure,
    classify_closure_result,
    closure_block_reason,
    closure_required_for_task,
    extract_task_closure,
)


def test_build_task_closure_marks_submit_true_only_when_all_checks_pass() -> None:
    closure = build_task_closure(
        latest_user_request="Fix report",
        changed_files=["report.py"],
        acceptance_checks=[
            {"name": "py_compile", "status": "passed", "evidence": "ok"},
            {"name": "table_shape", "status": "passed", "evidence": "ok"},
        ],
    )

    assert closure["can_submit"] is True
    assert closure["remaining_blockers"] == []


def test_build_task_closure_records_failed_checks_as_blockers() -> None:
    closure = build_task_closure(
        latest_user_request="Fix report",
        acceptance_checks=[
            {"name": "py_compile", "status": "passed"},
            {"name": "table_shape", "status": "failed"},
        ],
    )

    assert closure["can_submit"] is False
    assert closure["remaining_blockers"] == ["table_shape"]
    assert closure_block_reason(closure) == "Task closure reports remaining blockers: table_shape"


def test_extract_task_closure_from_task_closure_prefix() -> None:
    text = (
        "Done.\n"
        'TASK_CLOSURE: {"latest_user_request":"x","acceptance_checks":[{"name":"test","status":"passed"}],'
        '"remaining_blockers":[],"can_submit":true}'
    )

    closure = extract_task_closure(text)

    assert closure is not None
    assert closure["can_submit"] is True
    assert closure["acceptance_checks"][0]["name"] == "test"


def test_closure_required_when_acceptance_criteria_present() -> None:
    assert closure_required_for_task({"acceptance_criteria": ["must verify"]}) is True
    assert closure_required_for_task({"acceptance_criteria": []}) is False


def test_classify_closure_result_blocks_missing_contract() -> None:
    status, summary = classify_closure_result(
        "All done.",
        {"acceptance_criteria": ["run tests"]},
    )

    assert status == "blocked"
    assert summary == "BLOCKED: Task did not provide a task_closure contract"


def test_classify_closure_result_accepts_passing_contract() -> None:
    status, summary = classify_closure_result(
        'TASK_CLOSURE: {"acceptance_checks":[{"name":"pytest","status":"passed"}],"remaining_blockers":[],"can_submit":true}',
        {"acceptance_criteria": ["run tests"]},
    )

    assert status == "done"
    assert summary.startswith("TASK_CLOSURE:")
