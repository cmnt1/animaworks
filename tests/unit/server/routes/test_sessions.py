"""Unit tests for server/routes/sessions.py — Session management endpoints."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from httpx import ASGITransport, AsyncClient


def _make_test_app(animas_dir: Path | None = None, anima_names: list[str] | None = None):
    from fastapi import FastAPI

    from server.routes.sessions import create_sessions_router

    app = FastAPI()
    app.state.animas_dir = animas_dir or Path("/tmp/fake/animas")
    app.state.anima_names = anima_names or []
    router = create_sessions_router()
    app.include_router(router, prefix="/api")
    return app


# ── GET /animas/{name}/sessions ─────────────────────────


class TestListSessions:
    async def test_anima_not_found(self, tmp_path):
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/nobody/sessions")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Anima not found: nobody"

    @patch("core.config.models.load_model_config")
    @patch("server.routes.sessions.ConversationMemory")
    @patch("server.routes.sessions.ShortTermMemory")
    async def test_list_sessions_empty(
        self, mock_stm_cls, mock_conv_cls, mock_lmc, tmp_path,
    ):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        (anima_dir / "episodes").mkdir()

        # ConversationMemory mock
        mock_state = MagicMock()
        mock_state.turns = []
        mock_state.compressed_summary = ""
        mock_conv = MagicMock()
        mock_conv.load.return_value = mock_state
        mock_conv_cls.return_value = mock_conv

        # ShortTermMemory mock
        mock_stm = MagicMock()
        mock_stm._archive_dir = anima_dir / "shortterm" / "archive"
        mock_stm_cls.return_value = mock_stm

        app = _make_test_app(animas_dir=tmp_path, anima_names=["alice"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/sessions")

        data = resp.json()
        assert data["anima"] == "alice"
        assert data["active_conversation"] is None
        assert data["archived_sessions"] == []
        assert data["episodes"] == []
        assert data["transcripts"] == []


    @patch("core.config.models.load_model_config")
    @patch("server.routes.sessions.ConversationMemory")
    @patch("server.routes.sessions.ShortTermMemory")
    async def test_list_sessions_with_active_conversation(
        self, mock_stm_cls, mock_conv_cls, mock_lmc, tmp_path,
    ):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        (anima_dir / "episodes").mkdir()

        mock_turn = MagicMock()
        mock_turn.timestamp = "2026-01-01T12:00:00"

        mock_state = MagicMock()
        mock_state.turns = [mock_turn]
        mock_state.compressed_summary = ""
        mock_state.total_turn_count = 1

        mock_conv = MagicMock()
        mock_conv.load.return_value = mock_state
        mock_conv_cls.return_value = mock_conv

        mock_stm = MagicMock()
        mock_stm._archive_dir = anima_dir / "shortterm" / "archive"
        mock_stm_cls.return_value = mock_stm

        app = _make_test_app(animas_dir=tmp_path, anima_names=["alice"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/sessions")

        data = resp.json()
        assert data["active_conversation"] is not None
        assert data["active_conversation"]["exists"] is True
        assert data["active_conversation"]["turn_count"] == 1


class TestRecordVoiceCall:
    async def test_call_record_is_saved_and_returned_in_conversation_history(self, tmp_path):
        anima_dir = tmp_path / "alice"
        (anima_dir / "activity_log").mkdir(parents=True)
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        payload = {
            "started_at": "2026-10-28T12:00:00+09:00",
            "duration_seconds": 84,
            "thread_id": "default",
            "summary": "証明書の設定を確認しました。",
            "transcript": [
                {"speaker": "user", "text": "証明書の状態はどう？"},
                {"speaker": "assistant", "text": "設定を確認しました。"},
            ],
        }

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            saved = await client.post("/api/animas/alice/conversation/calls", json=payload)
            history = await client.get("/api/animas/alice/conversation/history")

        assert saved.status_code == 200
        assert saved.json()["ok"] is True
        assert history.status_code == 200
        messages = [message for session in history.json()["sessions"] for message in session["messages"]]
        call = next(message for message in messages if message.get("type") == "voice_call")
        assert call["content"] == payload["summary"]
        assert call["started_at"] == payload["started_at"]
        assert call["duration_seconds"] == 84
        assert call["transcript"] == payload["transcript"]

    async def test_call_record_survives_named_thread_file_fallback(self, tmp_path):
        anima_dir = tmp_path / "alice"
        thread_dir = anima_dir / "state" / "conversations"
        thread_dir.mkdir(parents=True)
        (anima_dir / "activity_log").mkdir()
        (thread_dir / "research.json").write_text(json.dumps({
            "turns": [
                {"role": "human", "timestamp": "2026-10-28T10:00:00+09:00", "content": "最初の質問"},
                {"role": "assistant", "timestamp": "2026-10-28T10:01:00+09:00", "content": "最初の回答"},
            ],
        }), encoding="utf-8")
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/animas/alice/conversation/calls", json={
                "started_at": "2026-10-28T12:00:00+09:00",
                "duration_seconds": 20,
                "thread_id": "research",
                "summary": "調査結果を伝えました。",
                "transcript": [],
            })
            history = await client.get("/api/animas/alice/conversation/history?thread_id=research")

        assert history.status_code == 200
        messages = [message for session in history.json()["sessions"] for message in session["messages"]]
        assert any(message.get("type") == "voice_call" for message in messages)


# ── GET /animas/{name}/sessions/{session_id} ────────────


class TestGetSessionDetail:
    async def test_anima_not_found(self, tmp_path):
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/nobody/sessions/123")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Anima not found: nobody"

    @patch("server.routes.sessions.ShortTermMemory")
    async def test_session_not_found(self, mock_stm_cls, tmp_path):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        archive_dir = anima_dir / "shortterm" / "archive"
        archive_dir.mkdir(parents=True)

        mock_stm = MagicMock()
        mock_stm._archive_dir = archive_dir
        mock_stm_cls.return_value = mock_stm

        app = _make_test_app(animas_dir=tmp_path, anima_names=["alice"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/sessions/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Session not found"

    @patch("server.routes.sessions.ShortTermMemory")
    async def test_session_detail_success(self, mock_stm_cls, tmp_path):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        archive_dir = anima_dir / "shortterm" / "archive"
        archive_dir.mkdir(parents=True)

        session_data = {"trigger": "heartbeat", "turn_count": 3}
        (archive_dir / "20260101.json").write_text(
            json.dumps(session_data), encoding="utf-8"
        )
        (archive_dir / "20260101.md").write_text("# Session log", encoding="utf-8")

        mock_stm = MagicMock()
        mock_stm._archive_dir = archive_dir
        mock_stm_cls.return_value = mock_stm

        app = _make_test_app(animas_dir=tmp_path, anima_names=["alice"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/sessions/20260101")

        data = resp.json()
        assert data["anima"] == "alice"
        assert data["session_id"] == "20260101"
        assert data["data"]["trigger"] == "heartbeat"
        assert data["markdown"] == "# Session log"

    @patch("server.routes.sessions.ShortTermMemory")
    async def test_session_corrupted_json(self, mock_stm_cls, tmp_path):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        archive_dir = anima_dir / "shortterm" / "archive"
        archive_dir.mkdir(parents=True)

        (archive_dir / "bad.json").write_text("not json", encoding="utf-8")

        mock_stm = MagicMock()
        mock_stm._archive_dir = archive_dir
        mock_stm_cls.return_value = mock_stm

        app = _make_test_app(animas_dir=tmp_path, anima_names=["alice"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/sessions/bad")
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Session data corrupted"


class TestNotificationReply:
    async def test_reply_routes_with_context_and_marks_notification_replied(self, tmp_path, monkeypatch):
        from core.activity.logger import ActivityLogger

        anima_dir = tmp_path / "alice"
        activity = ActivityLogger(anima_dir)
        notify = activity.log(
            "human_notify",
            content="Deploy after the certificate check.",
            meta={"subject": "Deployment", "priority": "normal"},
            ctx="chat",
        )
        monkeypatch.setattr("core.paths.get_shared_dir", lambda: tmp_path / "shared")
        monkeypatch.setattr("core.paths.get_animas_dir", lambda: tmp_path)

        messenger = MagicMock()
        with patch("core.messaging.messenger.Messenger", return_value=messenger):
            app = _make_test_app(animas_dir=tmp_path)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/animas/alice/notifications/reply",
                    json={"notification_id": notify.ts, "text": "Proceed with the certificate first."},
                )

        assert response.status_code == 200
        assert response.json()["replied"] is True
        delivery = messenger.receive_external.call_args.kwargs
        assert delivery["source"] == "web"
        assert "Deployment" in delivery["content"]
        assert "Deploy after the certificate check." in delivery["content"]
        assert "Proceed with the certificate first." in delivery["content"]
        assert delivery["external_thread_ts"] == notify.ts

        messages = [
            message
            for session in activity.get_conversation_view(limit=20)["sessions"]
            for message in session["messages"]
        ]
        notify_message = next(message for message in messages if message.get("type") == "human_notify")
        assert notify_message["replied"] is True
        assert notify_message["notification_id"] == notify.ts

    async def test_unknown_notification_returns_404(self, tmp_path):
        (tmp_path / "alice").mkdir()
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/animas/alice/notifications/reply",
                json={"notification_id": "missing", "text": "reply"},
            )
        assert response.status_code == 404


# ── GET /animas/{name}/transcripts/{date} ───────────────


class TestGetTranscript:
    async def test_anima_not_found(self, tmp_path):
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/nobody/transcripts/2026-01-01")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Anima not found: nobody"

    @patch("core.config.models.load_model_config")
    @patch("server.routes.sessions.ConversationMemory")
    async def test_get_transcript_success(self, mock_conv_cls, mock_lmc, tmp_path):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()

        mock_conv = MagicMock()
        mock_conv.load_transcript.return_value = [
            {"role": "user", "content": "Hello", "timestamp": "2026-01-01T12:00:00"}
        ]
        mock_conv_cls.return_value = mock_conv

        app = _make_test_app(animas_dir=tmp_path, anima_names=["alice"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/transcripts/2026-01-01")

        data = resp.json()
        assert data["anima"] == "alice"
        assert data["date"] == "2026-01-01"
        assert len(data["turns"]) == 1
