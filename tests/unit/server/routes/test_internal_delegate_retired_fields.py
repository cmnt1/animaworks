from __future__ import annotations

from server.routes.internal import DelegateTaskPersistRequest


def test_legacy_retired_fields_are_ignored() -> None:
    request = DelegateTaskPersistRequest.model_validate(
        {
            "delegator": "boss",
            "target": "worker",
            "instruction": "Review the report",
            "summary": "Review report",
            "sub_task_id": "123456789abc",
            "tracking_task_id": "abcdef123456",
            "deadline": "2026-09-27T18:00:00+09:00",
            "exclusive_key": "legacy-key",
            "persist_sub": False,
            "persist_tracking": False,
            "persist_pending": False,
        }
    )

    assert request.delegator == "boss"
    for field in ("deadline", "exclusive_key", "persist_sub", "persist_tracking", "persist_pending"):
        assert not hasattr(request, field)
