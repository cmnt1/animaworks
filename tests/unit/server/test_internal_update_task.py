from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from core.memory.task_queue import TaskQueueManager


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_internal_update_task_persists_meta_and_status(tmp_path, monkeypatch) -> None:
    from fastapi import FastAPI

    from server.routes.internal import create_internal_router

    animas_dir = tmp_path / "animas"
    anima_dir = animas_dir / "rin"
    (anima_dir / "state").mkdir(parents=True)
    manager = TaskQueueManager(anima_dir)
    entry = manager.add_task(
        source="anima",
        original_instruction="work",
        assignee="rin",
        summary="work",
    )
    monkeypatch.setattr("core.paths.get_animas_dir", lambda: animas_dir)
    app = FastAPI()
    app.state.ws_manager = MagicMock()
    app.include_router(create_internal_router(), prefix="/api")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/internal/update-task",
            json={
                "anima_name": "rin",
                "task_id": entry.task_id,
                "status": "done",
                "summary": "verified",
                "meta": {"completed_by": "agent_declaration", "result_note": "verified"},
            },
        )

    assert response.status_code == 200
    updated = manager.get_task_by_id(entry.task_id)
    assert updated is not None
    assert updated.status == "done"
    assert updated.summary == "verified"
    assert updated.meta["completed_by"] == "agent_declaration"
