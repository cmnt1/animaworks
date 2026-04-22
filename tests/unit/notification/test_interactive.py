# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for :mod:`core.notification.interactive`."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def data_dir(tmp_path):
    """Provide a temporary data directory."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()
    return tmp_path


@pytest.fixture
def _patch_dirs(data_dir):
    """Patch get_data_dir, get_shared_dir, and auth for stable approval tokens."""
    mock_auth = MagicMock()
    mock_auth.secret_key = "unit-test-secret-key"

    with (
        patch("core.notification.interactive.get_data_dir", return_value=data_dir),
        patch("core.notification.interactive.get_shared_dir", return_value=data_dir / "shared"),
        patch("core.notification.interactive.load_auth", return_value=mock_auth),
    ):
        import core.notification.interactive as mod

        mod._router = None
        yield
        mod._router = None


class TestInteractionRouter:
    """Tests for InteractionRouter."""

    @pytest.mark.asyncio
    async def test_create_returns_request(self, _patch_dirs):
        from core.notification.interactive import get_interaction_router

        router = get_interaction_router()
        req = await router.create("test_anima", "approval", ["approve", "reject"])
        assert req.callback_id
        assert req.anima_name == "test_anima"
        assert req.category == "approval"
        assert req.options == ["approve", "reject"]
        assert req.approval_token

    @pytest.mark.asyncio
    async def test_lookup_returns_created_request(self, _patch_dirs):
        from core.notification.interactive import get_interaction_router

        router = get_interaction_router()
        req = await router.create("test_anima", "approval", ["approve", "reject"])
        found = await router.lookup(req.callback_id)
        assert found is not None
        assert found.callback_id == req.callback_id

    @pytest.mark.asyncio
    async def test_lookup_returns_none_for_unknown(self, _patch_dirs):
        from core.notification.interactive import get_interaction_router

        router = get_interaction_router()
        found = await router.lookup("nonexistent")
        assert found is None

    @pytest.mark.asyncio
    async def test_resolve_injects_into_inbox(self, _patch_dirs):
        from core.notification.interactive import get_interaction_router

        router = get_interaction_router()
        req = await router.create("test_anima", "approval", ["approve", "reject"])

        with patch("core.messenger.Messenger") as mock_messenger:
            mock_instance = MagicMock()
            mock_messenger.return_value = mock_instance

            result = await router.resolve(req.callback_id, "approve", "tester", "slack")
            assert result is not None
            assert result.decision == "approve"
            assert result.actor == "tester"
            assert result.source == "slack"
            mock_instance.receive_external.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_returns_none_for_already_resolved(self, _patch_dirs):
        from core.notification.interactive import get_interaction_router

        router = get_interaction_router()
        req = await router.create("test_anima", "approval", ["approve", "reject"])

        with patch("core.messenger.Messenger"):
            result1 = await router.resolve(req.callback_id, "approve", "tester", "slack")
            result2 = await router.resolve(req.callback_id, "reject", "tester2", "slack")
            assert result1 is not None
            assert result2 is None

    @pytest.mark.asyncio
    async def test_verify_approval_token(self, _patch_dirs):
        from core.notification.interactive import get_interaction_router

        router = get_interaction_router()
        req = await router.create("test_anima", "approval", ["approve"])

        assert router.verify_approval_token(req.callback_id, req.approval_token)
        assert not router.verify_approval_token(req.callback_id, "wrong_token")

    @pytest.mark.asyncio
    async def test_update_message_ts(self, _patch_dirs):
        from core.notification.interactive import get_interaction_router

        router = get_interaction_router()
        req = await router.create("test_anima", "approval", ["approve"])
        await router.update_message_ts(req.callback_id, "slack", "1234.5678")

        found = await router.lookup(req.callback_id)
        assert found is not None
        assert found.message_ts.get("slack") == "1234.5678"

    @pytest.mark.asyncio
    async def test_prune_removes_old_entries(self, _patch_dirs):
        from core.notification.interactive import get_interaction_router

        router = get_interaction_router()
        req = await router.create("test_anima", "approval", ["approve"])

        count = await router.prune(max_age_days=0)
        assert count >= 1

        found = await router.lookup(req.callback_id)
        assert found is None


class TestBuildTextFallback:
    """Tests for build_text_fallback."""

    def test_basic_fallback(self):
        from core.notification.interactive import InteractionRequest, build_text_fallback

        req = InteractionRequest(
            callback_id="test123",
            anima_name="test",
            category="approval",
            options=["approve", "reject", "comment"],
            allowed_users={},
            metadata={},
            created_at=datetime.now(tz=UTC),
            approval_token="tok",
            message_ts={},
        )
        result = build_text_fallback(req)
        assert "[1]" in result
        assert "[2]" in result
        assert "[3]" in result
        assert "approve" in result.lower() or "Approve" in result

    def test_fallback_with_web_url(self):
        from core.notification.interactive import InteractionRequest, build_text_fallback

        req = InteractionRequest(
            callback_id="test123",
            anima_name="test",
            category="approval",
            options=["approve", "reject"],
            allowed_users={},
            metadata={},
            created_at=datetime.now(tz=UTC),
            approval_token="tok",
            message_ts={},
        )
        result = build_text_fallback(req, web_base_url="https://example.com")
        assert "https://example.com/api/approve/test123" in result
        assert "tok" in result
