"""Tests for core/tools/image_gen.py — Image generation pipeline."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import base64
import io
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.tools._base import ToolConfigError
from core.tools.image_gen import (
    FluxKontextClient,
    ImageGenPipeline,
    MeshyClient,
    NovelAIClient,
    PipelineResult,
    _image_to_data_uri,
    _retry,
    get_tool_schemas,
)


def _sample_image_bytes(fmt: str = "PNG", size: tuple[int, int] = (32, 24)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, (96, 128, 160)).save(buf, format=fmt)
    return buf.getvalue()

# ── _image_to_data_uri ───────────────────────────────────────────


class TestImageToDataUri:
    def test_basic(self):
        data = b"\x89PNG\r\n\x1a\n"
        result = _image_to_data_uri(data)
        assert result.startswith("data:image/png;base64,")
        decoded = base64.b64decode(result.split(",", 1)[1])
        assert decoded == data

    def test_custom_mime(self):
        result = _image_to_data_uri(b"test", mime="image/jpeg")
        assert result.startswith("data:image/jpeg;base64,")


# ── _retry ────────────────────────────────────────────────────────


class TestRetry:
    def test_success_first_try(self):
        fn = MagicMock(return_value="ok")
        result = _retry(fn)
        assert result == "ok"
        assert fn.call_count == 1

    def test_retry_on_retryable_status(self):
        resp_429 = MagicMock()
        resp_429.status_code = 429
        req = MagicMock()
        req.url = "http://test"
        error = httpx.HTTPStatusError("429", request=req, response=resp_429)

        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise error
            return "ok"

        with patch("core.tools.image_gen.time.sleep"):
            result = _retry(fn, max_retries=3, delay=0.01)
        assert result == "ok"
        assert call_count == 3

    def test_no_retry_on_non_retryable(self):
        resp_400 = MagicMock()
        resp_400.status_code = 400
        req = MagicMock()
        error = httpx.HTTPStatusError("400", request=req, response=resp_400)

        fn = MagicMock(side_effect=error)
        with pytest.raises(httpx.HTTPStatusError):
            _retry(fn, max_retries=3)
        assert fn.call_count == 1

    def test_retry_on_connect_error(self):
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.ConnectError("connection refused")
            return "ok"

        with patch("core.tools.image_gen.time.sleep"):
            result = _retry(fn, max_retries=2, delay=0.01)
        assert result == "ok"


# ── NovelAIClient ─────────────────────────────────────────────────


class TestNovelAIClient:
    @pytest.fixture(autouse=True)
    def _set_token(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("NOVELAI_TOKEN", "test-nai-token")

    def test_init(self):
        client = NovelAIClient()
        assert client._token == "test-nai-token"

    def test_missing_token(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("NOVELAI_TOKEN", raising=False)
        with pytest.raises(ToolConfigError):
            NovelAIClient()

    def test_extract_png_from_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("image.png", b"fake-png-data")
        raw = buf.getvalue()
        result = NovelAIClient._extract_png(raw)
        assert result == b"fake-png-data"

    def test_extract_png_no_png(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("image.jpg", b"data")
        with pytest.raises(ValueError, match="no PNG"):
            NovelAIClient._extract_png(buf.getvalue())

    def test_generate_fullbody(self):
        # Create a valid ZIP response
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("output.png", b"PNG-BYTES")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = zip_buf.getvalue()
        mock_resp.raise_for_status = MagicMock()

        with patch("core.tools.image_gen.httpx.post", return_value=mock_resp):
            client = NovelAIClient()
            result = client.generate_fullbody("1girl, black hair")
        assert result == b"PNG-BYTES"


# ── FluxKontextClient ─────────────────────────────────────────────


class TestFluxKontextClient:
    @pytest.fixture(autouse=True)
    def _set_key(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("FAL_KEY", "test-fal-key")

    def test_init(self):
        client = FluxKontextClient()
        assert client._key == "test-fal-key"

    def test_missing_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("FAL_KEY", raising=False)
        with pytest.raises(ToolConfigError):
            FluxKontextClient()


class TestDispatchGenerateIcon:
    @patch("core.tools._anima_icon_url.persist_anima_icon_path_template")
    @patch("core.tools.image_gen.FluxKontextClient")
    @patch("core.config.models.load_config")
    def test_writes_icon_png_with_square_aspect_ratio(
        self,
        mock_load_config: MagicMock,
        mock_flux_cls: MagicMock,
        _mock_persist: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        assets = tmp_path / "assets"
        assets.mkdir()
        (assets / "avatar_bustup.png").write_bytes(b"\x89PNG\r\n\x1a\nx")

        cfg = MagicMock()
        cfg.image_gen.image_style = "anime"
        cfg.image_gen.style_prefix = ""
        cfg.image_gen.style_suffix = ""
        mock_load_config.return_value = cfg

        mock_flux_cls.return_value.generate_from_reference.return_value = b"CHAT_ICON_BYTES"

        from core.tools.image_gen import dispatch

        result = dispatch("generate_icon", {"anima_dir": str(tmp_path)})
        assert "error" not in result
        assert str(result["path"]).endswith("icon.png")
        assert (assets / "icon.png").read_bytes() == b"CHAT_ICON_BYTES"
        kw = mock_flux_cls.return_value.generate_from_reference.call_args[1]
        assert kw["aspect_ratio"] == "1:1"

    @patch("core.tools._anima_icon_url.persist_anima_icon_path_template")
    @patch("core.tools.image_gen.FluxKontextClient")
    @patch("core.config.models.load_config")
    def test_writes_icon_realistic_png_when_realistic_style(
        self,
        mock_load_config: MagicMock,
        mock_flux_cls: MagicMock,
        _mock_persist: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        assets = tmp_path / "assets"
        assets.mkdir()
        (assets / "avatar_bustup_realistic.png").write_bytes(b"\x89PNG\r\n\x1a\nx")

        cfg = MagicMock()
        cfg.image_gen.image_style = "realistic"
        cfg.image_gen.style_prefix = ""
        cfg.image_gen.style_suffix = ""
        mock_load_config.return_value = cfg

        mock_flux_cls.return_value.generate_from_reference.return_value = b"ICON_REALISTIC"

        from core.tools.image_gen import dispatch

        result = dispatch("generate_icon", {"anima_dir": str(tmp_path)})
        assert "error" not in result
        assert str(result["path"]).endswith("icon_realistic.png")
        assert (assets / "icon_realistic.png").read_bytes() == b"ICON_REALISTIC"


# ── MeshyClient ───────────────────────────────────────────────────


class TestMeshyClient:
    @pytest.fixture(autouse=True)
    def _set_key(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("MESHY_API_KEY", "test-meshy-key")

    def test_init(self):
        client = MeshyClient()
        assert client._key == "test-meshy-key"

    def test_missing_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("MESHY_API_KEY", raising=False)
        with pytest.raises(ToolConfigError):
            MeshyClient()

    def test_headers(self):
        client = MeshyClient()
        headers = client._headers()
        assert headers["Authorization"] == "Bearer test-meshy-key"

    def test_download_model_missing_format(self):
        client = MeshyClient()
        task = {"model_urls": {"glb": "http://test/model.glb"}}
        with pytest.raises(ValueError, match="Format 'fbx' not available"):
            client.download_model(task, fmt="fbx")

    def test_download_rigged_model_missing_key(self):
        client = MeshyClient()
        task = {"result": {}}
        with pytest.raises(ValueError, match="missing"):
            client.download_rigged_model(task, fmt="glb")

    def test_download_animation_missing_key(self):
        client = MeshyClient()
        task = {"result": {}}
        with pytest.raises(ValueError, match="missing"):
            client.download_animation(task, fmt="glb")


# ── PipelineResult ────────────────────────────────────────────────


class TestPipelineResult:
    def test_defaults(self):
        r = PipelineResult()
        assert r.fullbody_path is None
        assert r.errors == []
        assert r.skipped == []

    def test_to_dict(self, tmp_path: Path):
        r = PipelineResult(
            fullbody_path=tmp_path / "fb.png",
            errors=["err1"],
            skipped=["bustup"],
        )
        d = r.to_dict()
        assert "fb.png" in d["fullbody"]
        assert d["errors"] == ["err1"]
        assert d["skipped"] == ["bustup"]

    def test_to_dict_empty(self):
        r = PipelineResult()
        d = r.to_dict()
        assert d["fullbody"] is None
        assert d["model"] is None
        assert d["animations"] == {}


# ── ImageGenPipeline ──────────────────────────────────────────────


class TestImageGenPipeline:
    def test_init(self, tmp_path: Path):
        pipe = ImageGenPipeline(tmp_path)
        assert pipe._anima_dir == tmp_path

    def test_generate_all_skips_existing(self, tmp_path: Path):
        from core.config.models import ImageGenConfig

        assets = tmp_path / "assets"
        assets.mkdir()
        (assets / "avatar_fullbody.png").write_bytes(b"existing")

        pipe = ImageGenPipeline(tmp_path, config=ImageGenConfig(image_style="anime"))
        # Only run fullbody step
        result = pipe.generate_all(
            prompt="test",
            skip_existing=True,
            steps=["fullbody"],
        )
        assert "fullbody" in result.skipped
        assert result.fullbody_path is not None

    def test_generate_all_no_fullbody_fails(self, tmp_path: Path):
        pipe = ImageGenPipeline(tmp_path)
        # Skip fullbody step -> no reference image
        result = pipe.generate_all(prompt="test", steps=["bustup"])
        assert len(result.errors) > 0

    def test_init_with_config(self, tmp_path: Path):
        from core.config.models import ImageGenConfig

        cfg = ImageGenConfig(image_style="anime", style_prefix="anime, ", vibe_strength=0.7)
        pipe = ImageGenPipeline(tmp_path, config=cfg)
        assert pipe._config is cfg
        assert pipe._config.style_prefix == "anime, "
        assert pipe._config.vibe_strength == 0.7

    def test_init_without_config_uses_default(self, tmp_path: Path):
        from core.config.models import ImageGenConfig

        pipe = ImageGenPipeline(tmp_path)
        assert isinstance(pipe._config, ImageGenConfig)
        assert pipe._config.style_reference is None
        assert pipe._config.style_prefix == ""
        assert pipe._config.vibe_strength == 0.6

    def test_generate_all_applies_style_prefix_suffix(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("NOVELAI_TOKEN", "test-token")
        from core.config.models import ImageGenConfig

        cfg = ImageGenConfig(
            image_style="anime",
            style_prefix="anime coloring, ",
            style_suffix=", high quality",
        )
        pipe = ImageGenPipeline(tmp_path, config=cfg)

        with patch("core.tools.image_gen.NovelAIClient") as mock_nai_cls:
            mock_client = MagicMock()
            mock_client.generate_fullbody.return_value = b"PNG-DATA"
            mock_nai_cls.return_value = mock_client

            pipe.generate_all(
                prompt="1girl, black hair",
                skip_existing=False,
                steps=["fullbody"],
            )

            call_kwargs = mock_client.generate_fullbody.call_args[1]
            assert call_kwargs["prompt"] == "anime coloring, 1girl, black hair, high quality"

    def test_generate_all_applies_negative_prompt_extra(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("NOVELAI_TOKEN", "test-token")
        from core.config.models import ImageGenConfig

        cfg = ImageGenConfig(image_style="anime", negative_prompt_extra="realistic, 3d render")
        pipe = ImageGenPipeline(tmp_path, config=cfg)

        with patch("core.tools.image_gen.NovelAIClient") as mock_nai_cls:
            mock_client = MagicMock()
            mock_client.generate_fullbody.return_value = b"PNG-DATA"
            mock_nai_cls.return_value = mock_client

            pipe.generate_all(
                prompt="1girl",
                negative_prompt="lowres, bad anatomy",
                skip_existing=False,
                steps=["fullbody"],
            )

            call_kwargs = mock_client.generate_fullbody.call_args[1]
            assert call_kwargs["negative_prompt"] == "lowres, bad anatomy, realistic, 3d render"

    def test_generate_all_applies_negative_prompt_extra_empty(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("NOVELAI_TOKEN", "test-token")
        from core.config.models import ImageGenConfig

        cfg = ImageGenConfig(image_style="anime", negative_prompt_extra="realistic")
        pipe = ImageGenPipeline(tmp_path, config=cfg)

        with patch("core.tools.image_gen.NovelAIClient") as mock_nai_cls:
            mock_client = MagicMock()
            mock_client.generate_fullbody.return_value = b"PNG-DATA"
            mock_nai_cls.return_value = mock_client

            pipe.generate_all(
                prompt="1girl",
                negative_prompt="",
                skip_existing=False,
                steps=["fullbody"],
            )

            call_kwargs = mock_client.generate_fullbody.call_args[1]
            assert call_kwargs["negative_prompt"] == "realistic"

    def test_generate_all_loads_style_reference(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("NOVELAI_TOKEN", "test-token")
        from core.config.models import ImageGenConfig

        style_ref = tmp_path / "style_ref.png"
        style_ref.write_bytes(b"STYLE-IMAGE-DATA")

        cfg = ImageGenConfig(image_style="anime", style_reference=str(style_ref))
        pipe = ImageGenPipeline(tmp_path, config=cfg)

        with patch("core.tools.image_gen.NovelAIClient") as mock_nai_cls:
            mock_client = MagicMock()
            mock_client.generate_fullbody.return_value = b"PNG-DATA"
            mock_nai_cls.return_value = mock_client

            pipe.generate_all(
                prompt="1girl",
                skip_existing=False,
                steps=["fullbody"],
            )

            call_kwargs = mock_client.generate_fullbody.call_args[1]
            assert call_kwargs["vibe_image"] == b"STYLE-IMAGE-DATA"

    def test_generate_all_warns_missing_style_reference(self, tmp_path: Path, monkeypatch, caplog):
        monkeypatch.setenv("NOVELAI_TOKEN", "test-token")
        import logging

        from core.config.models import ImageGenConfig

        cfg = ImageGenConfig(image_style="anime", style_reference="/nonexistent/path/style.png")
        pipe = ImageGenPipeline(tmp_path, config=cfg)

        with patch("core.tools.image_gen.NovelAIClient") as mock_nai_cls:
            mock_client = MagicMock()
            mock_client.generate_fullbody.return_value = b"PNG-DATA"
            mock_nai_cls.return_value = mock_client

            with caplog.at_level(logging.WARNING):
                pipe.generate_all(
                    prompt="1girl",
                    skip_existing=False,
                    steps=["fullbody"],
                )

            call_kwargs = mock_client.generate_fullbody.call_args[1]
            assert call_kwargs["vibe_image"] is None
            assert any("Style reference not found" in r.message for r in caplog.records)

    def test_generate_all_passes_vibe_params(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("NOVELAI_TOKEN", "test-token")
        from core.config.models import ImageGenConfig

        cfg = ImageGenConfig(image_style="anime", vibe_strength=0.3, vibe_info_extracted=0.5)
        pipe = ImageGenPipeline(tmp_path, config=cfg)

        with patch("core.tools.image_gen.NovelAIClient") as mock_nai_cls:
            mock_client = MagicMock()
            mock_client.generate_fullbody.return_value = b"PNG-DATA"
            mock_nai_cls.return_value = mock_client

            pipe.generate_all(
                prompt="1girl",
                skip_existing=False,
                steps=["fullbody"],
            )

            call_kwargs = mock_client.generate_fullbody.call_args[1]
            assert call_kwargs["vibe_strength"] == 0.3
            assert call_kwargs["vibe_info_extracted"] == 0.5

    def test_generate_all_uses_openai_generation_model(self, tmp_path: Path):
        from core.config.models import ImageGenConfig

        cfg = ImageGenConfig(image_style="realistic")
        pipe = ImageGenPipeline(tmp_path, config=cfg)

        with patch("core.tools.image.openai.OpenAIImageClient") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.generate_fullbody.return_value = b"PNG-DATA"
            mock_openai_cls.return_value = mock_client

            result = pipe.generate_all(
                prompt="realistic full body portrait",
                skip_existing=False,
                steps=["fullbody"],
                generation_model="openai:gpt-image-2",
                vibe_image=b"STYLE",
            )

            assert result.fullbody_path == tmp_path / "assets" / "avatar_fullbody_realistic.png"
            mock_openai_cls.assert_called_once_with(model="gpt-image-2")
            call_kwargs = mock_client.generate_fullbody.call_args[1]
            assert call_kwargs["vibe_image"] == b"STYLE"
            assert call_kwargs["face_reference_image"] is None

    def test_openai_image_client_uses_codex_subscription_image_gen(self, tmp_path: Path, monkeypatch):
        from core.tools.image.openai import OpenAIImageClient

        codex_home = tmp_path / "codex-home"
        codex_home.mkdir()
        seen: dict[str, object] = {}

        class FakePopen:
            pid = 12345

            def __init__(self, cmd, **kwargs):
                seen["cmd"] = cmd
                seen["env"] = kwargs["env"]
                self.returncode = 0

            def communicate(self, input=None, timeout=None):
                image_paths = [Path(seen["cmd"][index + 1]) for index, item in enumerate(seen["cmd"]) if item == "--image"]
                seen["reference_bytes"] = [path.read_bytes() for path in image_paths]
                instruction = input
                marker = "Save or copy the final generated image to this exact path:\n"
                output_path = Path(instruction.split(marker, 1)[1].split("\n", 1)[0])
                output_path.write_bytes(b"PNG-DATA")
                seen["input"] = instruction
                seen["instruction"] = instruction
                return str(output_path), ""

        def fake_popen(cmd, **kwargs):
            seen["cmd"] = cmd
            seen["env"] = kwargs["env"]
            return FakePopen(cmd, **kwargs)

        monkeypatch.setattr("core.tools.image.openai.get_codex_executable", lambda: "codex")
        monkeypatch.setattr(
            "server.routes.usage_routes.get_openai_subscription_codex_home",
            lambda refresh=False: codex_home,
        )
        monkeypatch.setattr("core.tools.image.openai.subprocess.Popen", fake_popen)

        img = OpenAIImageClient(model="gpt-image-2").generate_fullbody(
            prompt="portrait",
            vibe_image=_sample_image_bytes("PNG"),
            face_reference_image=_sample_image_bytes("JPEG"),
        )

        assert img == b"PNG-DATA"
        assert seen["cmd"][:2] == ["codex", "exec"]
        assert seen["cmd"][-1] == "-"
        assert seen["cmd"][seen["cmd"].index("--cd") + 1] != str(Path.cwd())
        assert seen["env"]["CODEX_HOME"] == str(codex_home)
        assert seen["input"] == seen["instruction"]
        assert seen["cmd"].count("--image") == 2
        assert all(data.startswith(b"\x89PNG\r\n\x1a\n") for data in seen["reference_bytes"])
        assert "style_reference.png" in seen["instruction"]
        assert "face_reference.png" in seen["instruction"]
        assert "use it as the face and identity reference" in seen["instruction"]
        assert "bust-up, head-and-shoulders character portrait" in seen["instruction"]
        assert "Use the built-in image generation tool with gpt-image-2" in seen["instruction"]

    def test_openai_image_client_reports_codex_failure(self, tmp_path: Path, monkeypatch):
        from core.tools.image.openai import OpenAIImageClient

        codex_home = tmp_path / "codex-home"
        codex_home.mkdir()

        class FakePopen:
            pid = 12345
            returncode = 1

            def __init__(self, cmd, **kwargs):
                pass

            def communicate(self, input=None, timeout=None):
                return "", "image tool failed"

        monkeypatch.setattr("core.tools.image.openai.get_codex_executable", lambda: "codex")
        monkeypatch.setattr(
            "server.routes.usage_routes.get_openai_subscription_codex_home",
            lambda refresh=False: codex_home,
        )
        monkeypatch.setattr("core.tools.image.openai.subprocess.Popen", FakePopen)

        with pytest.raises(RuntimeError, match="Codex image_gen failed"):
            OpenAIImageClient(model="gpt-image-2").generate_fullbody(prompt="portrait")

    def test_openai_image_client_rejects_invalid_reference_image(self, tmp_path: Path, monkeypatch):
        from core.tools.image.openai import OpenAIImageClient

        codex_home = tmp_path / "codex-home"
        codex_home.mkdir()

        monkeypatch.setattr("core.tools.image.openai.get_codex_executable", lambda: "codex")
        monkeypatch.setattr(
            "server.routes.usage_routes.get_openai_subscription_codex_home",
            lambda refresh=False: codex_home,
        )

        with pytest.raises(RuntimeError, match="face reference image could not be decoded"):
            OpenAIImageClient(model="gpt-image-2").generate_fullbody(
                prompt="portrait",
                face_reference_image=b"<html>not an image</html>",
            )

    def test_openai_image_client_retries_transient_stream_disconnect(self, tmp_path: Path, monkeypatch):
        from core.tools.image.openai import OpenAIImageClient

        codex_home = tmp_path / "codex-home"
        codex_home.mkdir()
        attempts: list[list[str]] = []
        sleeps: list[float] = []

        class FakePopen:
            pid = 12345

            def __init__(self, cmd, **kwargs):
                self.cmd = cmd
                self.returncode = 1 if not attempts else 0
                attempts.append(cmd)

            def communicate(self, input=None, timeout=None):
                if self.returncode:
                    return "", "ERROR: stream disconnected before completion: You can retry your request."
                marker = "Save or copy the final generated image to this exact path:\n"
                output_path = Path(input.split(marker, 1)[1].split("\n", 1)[0])
                output_path.write_bytes(b"PNG-DATA")
                return str(output_path), ""

        monkeypatch.setattr("core.tools.image.openai.get_codex_executable", lambda: "codex")
        monkeypatch.setattr(
            "server.routes.usage_routes.get_openai_subscription_codex_home",
            lambda refresh=False: codex_home,
        )
        monkeypatch.setattr("core.tools.image.openai.subprocess.Popen", FakePopen)
        monkeypatch.setattr("core.tools.image.openai.time.sleep", lambda wait: sleeps.append(wait))
        monkeypatch.setenv("ANIMAWORKS_CODEX_IMAGE_RETRY_DELAY_SEC", "0")

        img = OpenAIImageClient(model="gpt-image-2").generate_fullbody(prompt="portrait")

        assert img == b"PNG-DATA"
        assert len(attempts) == 2
        assert sleeps == [0.0]

    def test_openai_image_client_kills_process_tree_on_timeout(self, tmp_path: Path, monkeypatch):
        from core.tools.image.openai import OpenAIImageClient

        codex_home = tmp_path / "codex-home"
        codex_home.mkdir()
        killed: list[int] = []

        class FakePopen:
            pid = 24680
            returncode = None

            def __init__(self, cmd, **kwargs):
                pass

            def communicate(self, input=None, timeout=None):
                raise subprocess.TimeoutExpired(cmd="codex", timeout=timeout)

        monkeypatch.setattr("core.tools.image.openai.get_codex_executable", lambda: "codex")
        monkeypatch.setattr(
            "server.routes.usage_routes.get_openai_subscription_codex_home",
            lambda refresh=False: codex_home,
        )
        monkeypatch.setattr("core.tools.image.openai.subprocess.Popen", FakePopen)
        monkeypatch.setattr("core.tools.image.openai._terminate_process_tree", lambda pid: killed.append(pid))
        monkeypatch.setenv("ANIMAWORKS_CODEX_IMAGE_TIMEOUT_SEC", "1")

        with pytest.raises(RuntimeError, match="timed out"):
            OpenAIImageClient(model="gpt-image-2").generate_fullbody(prompt="portrait")

        assert killed == [24680]

    @patch("core.tools._anima_icon_url.persist_anima_icon_path_template")
    def test_generate_all_icon_step_uses_square_aspect_ratio(
        self,
        _mock_persist: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("FAL_KEY", "test-fal-key")
        from core.config.models import ImageGenConfig

        assets = tmp_path / "assets"
        assets.mkdir()
        (assets / "avatar_bustup.png").write_bytes(b"\x89PNG\r\n\x1a\nbust")

        pipe = ImageGenPipeline(tmp_path, config=ImageGenConfig(image_style="anime"))

        with patch("core.tools.image_gen.FluxKontextClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.generate_from_reference.return_value = b"ICON-BYTES"
            mock_cls.return_value = mock_client

            result = pipe.generate_all(
                prompt="ignored",
                skip_existing=False,
                steps=["icon"],
            )

        mock_client.generate_from_reference.assert_called_once()
        kw = mock_client.generate_from_reference.call_args.kwargs
        assert kw["aspect_ratio"] == "1:1"
        assert kw["guidance_scale"] == 4.0
        assert result.icon_path == tmp_path / "assets" / "icon.png"
        assert result.icon_path.read_bytes() == b"ICON-BYTES"


# ── get_tool_schemas ──────────────────────────────────────────────


class TestGetToolSchemas:
    def test_returns_empty_list(self):
        """External tool modules return empty schema lists (schemas from dispatch layer)."""
        schemas = get_tool_schemas()
        assert isinstance(schemas, list)
        assert schemas == []
