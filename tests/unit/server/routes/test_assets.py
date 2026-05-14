"""Unit tests for server/routes/assets.py — Asset serving endpoints."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from core.config.models import ImageGenConfig
from core.tools.image_gen import PipelineResult


def _make_test_app(animas_dir: Path | None = None):
    from fastapi import FastAPI

    from server.routes.assets import create_assets_router

    app = FastAPI()
    app.state.animas_dir = animas_dir or Path("/tmp/fake/animas")
    app.state.ws_manager = MagicMock()
    app.state.ws_manager.broadcast = AsyncMock()
    router = create_assets_router()
    app.include_router(router, prefix="/api")
    return app


# Image model catalog endpoints


class TestImageModelCatalog:
    async def test_get_image_models_returns_known_nanogpt_models(self, tmp_path):
        app = _make_test_app(animas_dir=tmp_path / "animas")
        transport = ASGITransport(app=app)

        with patch("server.routes.assets.get_data_dir", return_value=tmp_path):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/assets/image-models")

        assert resp.status_code == 200
        data = resp.json()
        values = {model["value"] for model in data["models"]}
        assert "openai:gpt-image-2" in values
        assert "nanogpt:chroma" in values
        assert "nanogpt:hidream" in values
        gpt_image_2 = next(model for model in data["models"] if model["value"] == "openai:gpt-image-2")
        assert gpt_image_2["image_to_image"] is True
        hidream = next(model for model in data["models"] if model["value"] == "nanogpt:hidream")
        assert hidream["image_to_image"] is True

    async def test_refresh_image_models_caches_api_models_and_allows_generation_model(self, tmp_path):
        app = _make_test_app(animas_dir=tmp_path / "animas")
        transport = ASGITransport(app=app)
        api_models = [
            {
                "id": "new-image-model",
                "label": "New Image Model",
                "provider": "nanogpt",
                "image_to_image": True,
                "source": "api",
            }
        ]

        with (
            patch("server.routes.assets.get_data_dir", return_value=tmp_path),
            patch("server.routes.assets._nanogpt_image_api_key", return_value="test-key"),
            patch("server.routes.assets._list_nanogpt_image_models", return_value=api_models),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/assets/image-models/refresh")

            assert resp.status_code == 200
            data = resp.json()
            nanogpt_provider = next(provider for provider in data["providers"] if provider["provider"] == "nanogpt")
            assert nanogpt_provider["dynamic"] is True
            assert any(model["value"] == "nanogpt:new-image-model" for model in data["models"])

            from server.routes.assets import RemakePreviewRequest

            parsed = RemakePreviewRequest.model_validate({})
            assert parsed.generation_model == "openai:gpt-image-2"
            parsed = RemakePreviewRequest.model_validate({"generation_model": ""})
            assert parsed.generation_model is None
            parsed = RemakePreviewRequest.model_validate({"generation_model": "nanogpt:new-image-model"})
            assert parsed.generation_model == "nanogpt:new-image-model"
            parsed = RemakePreviewRequest.model_validate({"generation_model": "openai:gpt-image-2"})
            assert parsed.generation_model == "openai:gpt-image-2"


# ── GET /animas/{name}/assets ───────────────────────────


class TestIdentityAppearancePrompt:
    def test_prefers_identity_appearance_field_over_cached_prompt(self, tmp_path):
        from server.routes.assets import _identity_appearance_prompt

        anima_dir = tmp_path / "alice"
        assets_dir = anima_dir / "assets"
        assets_dir.mkdir(parents=True)
        (assets_dir / "prompt_realistic.txt").write_text("generic cached office portrait\n", encoding="utf-8")
        (anima_dir / "identity.md").write_text(
            "# Alice\n\n"
            "## \u5916\u898b\n"
            "\u5916\u898b: realistic, young Japanese woman, thin-framed glasses, half-up black hair, soft cardigan\n",
            encoding="utf-8",
        )

        prompt = _identity_appearance_prompt(anima_dir, name="alice", style="realistic")

        assert prompt is not None
        assert "thin-framed glasses" in prompt
        assert "half-up black hair" in prompt
        assert "generic cached" not in prompt

    def test_openai_identity_appearance_can_use_bustup_composition(self, tmp_path):
        from server.routes.assets import _identity_appearance_prompt

        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        (anima_dir / "identity.md").write_text(
            "# Alice\n\n"
            "## \u5916\u898b\n"
            "\u5916\u898b: realistic, young Japanese woman, thin-framed glasses, half-up black hair\n",
            encoding="utf-8",
        )

        prompt = _identity_appearance_prompt(anima_dir, name="alice", style="realistic", composition="bustup")

        assert prompt is not None
        assert "bust-up head-and-shoulders portrait" in prompt
        assert "thin-framed glasses" in prompt
        assert "full-length" not in prompt

    def test_uses_identity_appearance_heading_when_field_is_absent(self, tmp_path):
        from server.routes.assets import _identity_appearance_prompt

        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        (anima_dir / "identity.md").write_text(
            "# Alice\n\n"
            "## \u5916\u898b\n"
            "\u77e5\u7684\u3067\u843d\u3061\u7740\u3044\u305f\u96f0\u56f2\u6c17\u306e\u5973\u6027\u3002\n"
            "\u9577\u3081\u306e\u9ed2\u9aea\u3092\u30cf\u30fc\u30d5\u30a2\u30c3\u30d7\u306b\u307e\u3068\u3081\u3066\u3044\u308b\u3002\n\n"
            "## Personality\n"
            "Calm.\n",
            encoding="utf-8",
        )

        prompt = _identity_appearance_prompt(anima_dir, name="alice", style="realistic")

        assert prompt is not None
        assert "\u77e5\u7684\u3067\u843d\u3061\u7740\u3044\u305f" in prompt
        assert "Calm" not in prompt


class TestListAssets:
    async def test_anima_not_found(self, tmp_path):
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/nobody/assets")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Anima not found: nobody"

    async def test_no_assets_dir(self, tmp_path):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/assets")
        assert resp.status_code == 200
        assert resp.json()["assets"] == []

    async def test_list_assets(self, tmp_path):
        animas_dir = tmp_path / "animas"
        anima_dir = animas_dir / "alice"
        anima_dir.mkdir(parents=True)
        assets_dir = anima_dir / "assets"
        assets_dir.mkdir()
        (assets_dir / "avatar.png").write_bytes(b"\x89PNG")
        (assets_dir / "model.glb").write_bytes(b"\x00")

        app = _make_test_app(animas_dir=animas_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/assets")
        data = resp.json()
        assert len(data["assets"]) == 2
        names = [a["name"] for a in data["assets"]]
        assert "avatar.png" in names
        assert "model.glb" in names


# ── GET /animas/{name}/assets/metadata ──────────────────


class TestGetAssetMetadata:
    async def test_anima_not_found(self, tmp_path):
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/nobody/assets/metadata")
        assert resp.status_code == 404

    async def test_metadata_no_assets(self, tmp_path):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        (anima_dir / "identity.md").write_text("# Alice", encoding="utf-8")

        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/assets/metadata")
        data = resp.json()
        assert data["name"] == "alice"
        assert data["assets"] == {}

    async def test_metadata_with_color(self, tmp_path):
        animas_dir = tmp_path / "animas"
        anima_dir = animas_dir / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "identity.md").write_text(
            "# Alice\nイメージカラー: ピンク #FF69B4\n", encoding="utf-8"
        )
        (anima_dir / "assets").mkdir()

        app = _make_test_app(animas_dir=animas_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/assets/metadata")
        data = resp.json()
        assert data["colors"] == {"image_color": "#FF69B4"}

    async def test_metadata_with_assets_and_animations(self, tmp_path):
        animas_dir = tmp_path / "animas"
        anima_dir = animas_dir / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "identity.md").write_text("# Alice", encoding="utf-8")
        assets_dir = anima_dir / "assets"
        assets_dir.mkdir()
        (assets_dir / "avatar_fullbody.png").write_bytes(b"\x89PNG")
        (assets_dir / "avatar_chibi.glb").write_bytes(b"\x00")
        (assets_dir / "anim_idle.glb").write_bytes(b"\x00")
        (assets_dir / "anim_walk.glb").write_bytes(b"\x00")

        app = _make_test_app(animas_dir=animas_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/assets/metadata")
        data = resp.json()
        assert "avatar_fullbody" in data["assets"]
        assert "model_chibi" in data["assets"]
        assert "idle" in data["animations"]
        assert "walk" in data["animations"]


# ── GET/HEAD /animas/{name}/assets/{filename} ───────────


class TestGetAsset:
    async def test_anima_not_found(self, tmp_path):
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/nobody/assets/file.png")
        assert resp.status_code == 404

    async def test_invalid_filename(self, tmp_path):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/assets/..%2Fetc%2Fpasswd")
        assert resp.status_code in (400, 404)

    async def test_asset_not_found(self, tmp_path):
        animas_dir = tmp_path / "animas"
        anima_dir = animas_dir / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "assets").mkdir()
        app = _make_test_app(animas_dir=animas_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/assets/missing.png")
        assert resp.status_code == 404

    async def test_serve_png(self, tmp_path):
        animas_dir = tmp_path / "animas"
        anima_dir = animas_dir / "alice"
        anima_dir.mkdir(parents=True)
        assets_dir = anima_dir / "assets"
        assets_dir.mkdir()
        (assets_dir / "avatar.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        app = _make_test_app(animas_dir=animas_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/assets/avatar.png")
        assert resp.status_code == 200
        assert "image/png" in resp.headers.get("content-type", "")

    async def test_serve_glb(self, tmp_path):
        animas_dir = tmp_path / "animas"
        anima_dir = animas_dir / "alice"
        anima_dir.mkdir(parents=True)
        assets_dir = anima_dir / "assets"
        assets_dir.mkdir()
        (assets_dir / "model.glb").write_bytes(b"\x00\x00\x00\x00")

        app = _make_test_app(animas_dir=animas_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/assets/model.glb")
        assert resp.status_code == 200
        assert "model/gltf-binary" in resp.headers.get("content-type", "")

    async def test_head_request(self, tmp_path):
        animas_dir = tmp_path / "animas"
        anima_dir = animas_dir / "alice"
        anima_dir.mkdir(parents=True)
        assets_dir = anima_dir / "assets"
        assets_dir.mkdir()
        (assets_dir / "avatar.png").write_bytes(b"\x89PNG")

        app = _make_test_app(animas_dir=animas_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.head("/api/animas/alice/assets/avatar.png")
        assert resp.status_code == 200


class TestGetAttachment:
    async def test_serve_attachment(self, tmp_path):
        animas_dir = tmp_path / "animas"
        anima_dir = animas_dir / "alice"
        attachment_dir = anima_dir / "attachments"
        attachment_dir.mkdir(parents=True)
        (attachment_dir / "uploaded.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        app = _make_test_app(animas_dir=animas_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/animas/alice/attachments/uploaded.png")
        assert resp.status_code == 200
        assert "image/png" in resp.headers.get("content-type", "")


# ── POST /animas/{name}/assets/generate ─────────────────


class TestGenerateAssets:
    async def test_anima_not_found(self, tmp_path):
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/animas/nobody/assets/generate",
                json={"prompt": "a character"},
            )
        assert resp.status_code == 404

    async def test_missing_prompt(self, tmp_path):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/animas/alice/assets/generate",
                json={},
            )
        assert resp.status_code == 400
        assert "prompt is required" in resp.json()["detail"]

    @patch("core.tools.image_gen.ImageGenPipeline")
    async def test_generate_success(self, mock_pipeline_cls, tmp_path):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()

        mock_result = MagicMock()
        mock_result.fullbody_path = Path("/tmp/fb.png")
        mock_result.bustup_path = None
        mock_result.icon_path = None
        mock_result.chibi_path = None
        mock_result.model_path = None
        mock_result.rigged_model_path = None
        mock_result.animation_paths = {}
        mock_result.errors = []
        mock_result.to_dict.return_value = {"status": "done"}

        mock_pipeline = MagicMock()
        mock_pipeline.generate_all.return_value = mock_result
        mock_pipeline_cls.return_value = mock_pipeline

        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/animas/alice/assets/generate",
                json={"prompt": "anime girl"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "done"

    @patch("core.tools.image_gen.ImageGenPipeline")
    @patch("core.config.models.load_config")
    async def test_generate_uses_global_image_backend(self, mock_load_config, mock_pipeline_cls, tmp_path):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()

        mock_result = MagicMock()
        mock_result.fullbody_path = None
        mock_result.bustup_path = None
        mock_result.chibi_path = None
        mock_result.model_path = None
        mock_result.rigged_model_path = None
        mock_result.animation_paths = {}
        mock_result.errors = []
        mock_result.to_dict.return_value = {"status": "done"}

        mock_pipeline = MagicMock()
        mock_pipeline.generate_all.return_value = mock_result
        mock_pipeline_cls.return_value = mock_pipeline

        mock_load_config.return_value = MagicMock(image_gen=ImageGenConfig(backend="diffusers", image_style="anime"))
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/animas/alice/assets/generate",
                json={"prompt": "anime girl", "image_style": "realistic"},
            )

        assert resp.status_code == 200
        config = mock_pipeline_cls.call_args.kwargs["config"]
        assert config.backend == "diffusers"
        assert config.image_style == "realistic"

# ── GET /animas/{name}/assets/metadata (icon cross-mode fallback) ──


class TestGetAssetMetadataIconFallback:
    """icon.png / icon_realistic.png fallback for the opposite mode's gallery keys."""

    async def test_only_icon_png_fills_realistic_slot(self, tmp_path):
        anima_dir = tmp_path / "alice"
        assets_dir = anima_dir / "assets"
        assets_dir.mkdir(parents=True)
        (assets_dir / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 8)

        mock_cfg = MagicMock()
        mock_cfg.image_gen.image_style = "anime"

        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        with patch("core.config.models.load_config", return_value=mock_cfg):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/animas/alice/assets/metadata")
        assert resp.status_code == 200
        data = resp.json()
        assert data["assets"]["avatar_icon"]["filename"] == "icon.png"
        assert data["assets_realistic"]["avatar_icon_realistic"]["filename"] == "icon.png"
        assert data["assets_realistic"]["avatar_icon_realistic"]["url"].endswith("/icon.png")

    async def test_only_icon_realistic_fills_anime_slot(self, tmp_path):
        anima_dir = tmp_path / "bob"
        assets_dir = anima_dir / "assets"
        assets_dir.mkdir(parents=True)
        (assets_dir / "icon_realistic.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"y" * 8)

        mock_cfg = MagicMock()
        mock_cfg.image_gen.image_style = "realistic"

        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        with patch("core.config.models.load_config", return_value=mock_cfg):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/animas/bob/assets/metadata")
        assert resp.status_code == 200
        data = resp.json()
        assert data["assets_realistic"]["avatar_icon_realistic"]["filename"] == "icon_realistic.png"
        assert data["assets"]["avatar_icon"]["filename"] == "icon_realistic.png"
        assert data["assets"]["avatar_icon"]["url"].endswith("/icon_realistic.png")


# ── POST /animas/{name}/assets/regenerate-step ───────────


class TestRegenerateAssetStep:
    async def test_anima_not_found(self, tmp_path):
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/animas/nobody/assets/regenerate-step",
                json={"step": "icon"},
            )
        assert resp.status_code == 404

    async def test_fullbody_requires_prompt_or_prompt_txt(self, tmp_path):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        (anima_dir / "assets").mkdir()

        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        with patch("core.asset_reconciler._resolve_prompt", return_value=""):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/animas/alice/assets/regenerate-step",
                    json={"step": "fullbody", "prompt": ""},
                )
        assert resp.status_code == 400
        assert "prompt is required" in resp.json()["detail"]

    @patch("server.routes.assets.emit", new_callable=AsyncMock)
    @patch("core.tools.image_gen.ImageGenPipeline")
    async def test_icon_step_ok_and_emits(self, mock_pipeline_cls, mock_emit, tmp_path):
        anima_dir = tmp_path / "alice"
        (anima_dir / "assets").mkdir(parents=True)

        icon_path = anima_dir / "assets" / "icon.png"
        mock_pipeline = MagicMock()
        mock_pipeline.generate_all.return_value = PipelineResult(
            icon_path=icon_path,
            errors=[],
        )
        mock_pipeline_cls.return_value = mock_pipeline
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/animas/alice/assets/regenerate-step",
                json={"step": "icon"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["icon"] == str(icon_path)
        mock_emit.assert_awaited()
        call_kw = mock_emit.call_args[0]
        assert call_kw[1] == "anima.assets_updated"
        assert call_kw[2]["assets"] == ["icon.png"]
        assert call_kw[2]["errors"] == []

        mock_pipeline.generate_all.assert_called_once()
        ga_kw = mock_pipeline.generate_all.call_args[1]
        assert ga_kw["steps"] == ["icon"]
        assert ga_kw["skip_existing"] is False


# ── POST /animas/{name}/assets/remake-preview ───────────


class TestRemakePreview:
    @patch("core.tools.image_gen.ImageGenPipeline")
    @patch("core.config.models.load_config")
    async def test_without_style_from_ignores_global_style_reference(
        self,
        mock_load_config,
        mock_pipeline_cls,
        tmp_path,
    ):
        import asyncio

        animas_dir = tmp_path / "animas"
        anima_dir = animas_dir / "alice"
        assets_dir = anima_dir / "assets"
        assets_dir.mkdir(parents=True)
        (anima_dir / "identity.md").write_text("# Alice\n", encoding="utf-8")
        (assets_dir / "avatar_fullbody_realistic.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        global_style_ref = tmp_path / "global-style.png"
        global_style_ref.write_bytes(b"\x89PNG\r\n\x1a\n")
        mock_load_config.return_value = MagicMock(
            image_gen=ImageGenConfig(
                backend="diffusers",
                image_style="anime",
                style_reference=str(global_style_ref),
            ),
        )

        mock_pipeline = MagicMock()
        mock_pipeline.generate_all.return_value = MagicMock(errors=[])
        mock_pipeline_cls.return_value = mock_pipeline

        app = _make_test_app(animas_dir=animas_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/animas/alice/assets/remake-preview",
                json={"image_style": "realistic", "prompt": "portrait"},
            )

        assert resp.status_code == 202

        config = mock_pipeline_cls.call_args.kwargs["config"]
        assert config.image_style == "realistic"
        assert config.style_reference is None

        await asyncio.sleep(0.05)
        mock_pipeline.generate_all.assert_called_once()
        ga_kw = mock_pipeline.generate_all.call_args.kwargs
        assert "vibe_image" not in ga_kw

    @patch("core.tools.image_gen.ImageGenPipeline")
    @patch("core.config.models.load_config")
    async def test_remake_preview_uses_identity_appearance_before_cached_prompt(
        self,
        mock_load_config,
        mock_pipeline_cls,
        tmp_path,
    ):
        import asyncio

        animas_dir = tmp_path / "animas"
        anima_dir = animas_dir / "alice"
        assets_dir = anima_dir / "assets"
        assets_dir.mkdir(parents=True)
        (anima_dir / "identity.md").write_text(
            "# Alice\n\n"
            "## \u5916\u898b\n"
            "\u5916\u898b: realistic, young Japanese woman, thin-framed glasses, half-up black hair\n",
            encoding="utf-8",
        )
        (assets_dir / "prompt_realistic.txt").write_text("generic cached office portrait\n", encoding="utf-8")
        (assets_dir / "avatar_fullbody_realistic.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        mock_load_config.return_value = MagicMock(image_gen=ImageGenConfig(backend="diffusers", image_style="realistic"))
        mock_pipeline = MagicMock()
        mock_pipeline.generate_all.return_value = MagicMock(errors=[])
        mock_pipeline_cls.return_value = mock_pipeline

        app = _make_test_app(animas_dir=animas_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/animas/alice/assets/remake-preview",
                json={"image_style": "realistic"},
            )

        assert resp.status_code == 202

        await asyncio.sleep(0.05)
        prompt = mock_pipeline.generate_all.call_args.kwargs["prompt"]
        assert "bust-up head-and-shoulders portrait" in prompt
        assert "thin-framed glasses" in prompt
        assert "half-up black hair" in prompt
        assert "generic cached" not in prompt


# ── POST /animas/{name}/assets/upload-fullbody ──────────


class TestUploadFullbodyAsset:
    _PNG_MIN = b"\x89PNG\r\n\x1a\n" + b"x" * 8

    async def test_anima_not_found(self, tmp_path):
        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/animas/nobody/assets/upload-fullbody",
                files={"file": ("f.png", self._PNG_MIN, "image/png")},
                data={"image_style": "anime"},
            )
        assert resp.status_code == 404

    async def test_rejects_too_short_file(self, tmp_path):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()

        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/animas/alice/assets/upload-fullbody",
                files={"file": ("f.png", b"short", "image/png")},
                data={"image_style": "anime"},
            )
        assert resp.status_code == 400
        assert "invalid" in resp.json()["detail"].lower()

    async def test_rejects_non_image_bytes(self, tmp_path):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()

        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/animas/alice/assets/upload-fullbody",
                files={"file": ("f.bin", b"\x00" * 16, "application/octet-stream")},
                data={"image_style": "anime"},
            )
        assert resp.status_code == 400
        assert "PNG or JPEG" in resp.json()["detail"]

    @patch("server.routes.assets.emit", new_callable=AsyncMock)
    async def test_writes_anime_fullbody_png(self, mock_emit, tmp_path):
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()

        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/animas/alice/assets/upload-fullbody",
                files={"file": ("fb.png", self._PNG_MIN, "image/png")},
                data={"image_style": "anime"},
            )
        assert resp.status_code == 200
        out = anima_dir / "assets" / "avatar_fullbody.png"
        assert out.is_file()
        assert out.read_bytes() == self._PNG_MIN
        data = resp.json()
        assert data["filename"] == "avatar_fullbody.png"
        assert data["url"].endswith("/avatar_fullbody.png")
        mock_emit.assert_awaited_once()

    @patch("server.routes.assets.emit", new_callable=AsyncMock)
    async def test_writes_realistic_fullbody_png(self, mock_emit, tmp_path):
        anima_dir = tmp_path / "bob"
        anima_dir.mkdir()

        app = _make_test_app(animas_dir=tmp_path)
        transport = ASGITransport(app=app)
        jpeg = b"\xff\xd8\xff" + b"z" * 16
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/animas/bob/assets/upload-fullbody",
                files={"file": ("fb.jpg", jpeg, "image/jpeg")},
                data={"image_style": "realistic"},
            )
        assert resp.status_code == 200
        out = anima_dir / "assets" / "avatar_fullbody_realistic.png"
        assert out.read_bytes() == jpeg
        assert resp.json()["filename"] == "avatar_fullbody_realistic.png"
