# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""E2E-style tests for interactive approval (router, inbox, web API)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.routes.approve import create_approve_router


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    (tmp_path / "run").mkdir(parents=True)
    (tmp_path / "shared").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def approval_env(data_dir: Path):
    """Isolated interaction storage + shared inbox + stable auth secret."""
    mock_auth = MagicMock()
    mock_auth.secret_key = "e2e-approval-secret"

    with (
        patch("core.notification.interactive.get_data_dir", return_value=data_dir),
        patch("core.notification.interactive.get_shared_dir", return_value=data_dir / "shared"),
        patch("core.notification.interactive.load_auth", return_value=mock_auth),
    ):
        import core.notification.interactive as interactive_mod

        interactive_mod._router = None
        yield data_dir
        interactive_mod._router = None


class TestInteractiveApprovalFlow:
    """Full router → Messenger → inbox flow."""

    def test_resolve_writes_inbox_and_idempotent_resolve(self, approval_env: Path):
        from core.notification.interactive import get_interaction_router

        router = get_interaction_router()

        async def _run():
            req = await router.create("e2e_anima", "approval", ["approve", "reject"])
            r1 = await router.resolve(req.callback_id, "approve", "human", "e2e")
            assert r1 is not None
            r2 = await router.resolve(req.callback_id, "reject", "other", "e2e")
            assert r2 is None
            gone = await router.lookup(req.callback_id)
            assert gone is None
            return req.callback_id

        import asyncio

        callback_id = asyncio.run(_run())

        inbox = approval_env / "shared" / "inbox" / "e2e_anima"
        files = list(inbox.glob("*.json"))
        assert len(files) == 1
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        assert "approve" in payload.get("content", "").lower()
        assert callback_id in payload.get("content", "")


class TestApproveWebApi:
    """FastAPI approval routes with TestClient."""

    @pytest.fixture
    def client(self, approval_env: Path):
        app = FastAPI()
        app.include_router(create_approve_router(), prefix="/api")
        return TestClient(app)

    def test_get_returns_html(self, client: TestClient, approval_env: Path):
        from core.notification.interactive import get_interaction_router

        async def setup():
            return await get_interaction_router().create("web_anima", "approval", ["yes", "no"])

        import asyncio

        req = asyncio.run(setup())
        r = client.get(
            f"/api/approve/{req.callback_id}",
            params={"token": req.approval_token},
        )
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        assert "__APPROVAL_CONTEXT__" not in r.text
        assert req.callback_id in r.text

    def test_post_resolves(self, client: TestClient, approval_env: Path):
        from core.notification.interactive import get_interaction_router

        async def setup():
            return await get_interaction_router().create("web_anima", "approval", ["yes", "no"])

        import asyncio

        req = asyncio.run(setup())
        r = client.post(
            f"/api/approve/{req.callback_id}",
            json={
                "token": req.approval_token,
                "decision": "yes",
                "actor": "web_tester",
                "comment": "",
            },
        )
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_post_wrong_token_403(self, client: TestClient, approval_env: Path):
        from core.notification.interactive import get_interaction_router

        async def setup():
            return await get_interaction_router().create("web_anima", "approval", ["a"])

        import asyncio

        req = asyncio.run(setup())
        r = client.post(
            f"/api/approve/{req.callback_id}",
            json={"token": "bad", "decision": "a"},
        )
        assert r.status_code == 403

    def test_post_already_resolved_409(self, client: TestClient, approval_env: Path):
        from core.notification.interactive import get_interaction_router

        async def setup():
            return await get_interaction_router().create("web_anima", "approval", ["a"])

        import asyncio

        req = asyncio.run(setup())
        first = client.post(
            f"/api/approve/{req.callback_id}",
            json={"token": req.approval_token, "decision": "a"},
        )
        assert first.status_code == 200
        second = client.post(
            f"/api/approve/{req.callback_id}",
            json={"token": req.approval_token, "decision": "a"},
        )
        assert second.status_code == 409
