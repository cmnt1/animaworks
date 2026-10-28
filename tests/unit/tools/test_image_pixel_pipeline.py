"""Pixel-step integration tests for ImageGenPipeline."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config.models import ImageGenConfig
from core.integrations.image_gen import ImageGenPipeline


def _anima_dir(tmp_path: Path) -> Path:
    anima_dir = tmp_path / "anima"
    assets = anima_dir / "assets"
    assets.mkdir(parents=True)
    (assets / "avatar_fullbody.png").write_bytes(b"fullbody")
    return anima_dir


class TestPixelPipelineStep:
    def test_codex_unavailable_skips_without_error(self, tmp_path: Path) -> None:
        anima_dir = _anima_dir(tmp_path)
        pipeline = ImageGenPipeline(anima_dir, config=ImageGenConfig(image_style="anime"))

        with patch("core.integrations._image_pipeline.codex_available", return_value=False):
            result = pipeline.generate_all("prompt", steps=["pixel"], skip_existing=True)

        assert result.skipped == ["pixel"]
        assert result.errors == []
        assert result.pixel_sheet_path is None
        assert not (anima_dir / "assets" / "pixel_sheet.png").exists()

    def test_existing_sheet_is_skipped(self, tmp_path: Path) -> None:
        anima_dir = _anima_dir(tmp_path)
        sheet = anima_dir / "assets" / "pixel_sheet.png"
        sheet.write_bytes(b"existing")
        pipeline = ImageGenPipeline(anima_dir, config=ImageGenConfig(image_style="anime"))

        with (
            patch("core.integrations._image_pipeline.codex_available", return_value=True),
            patch("core.integrations._image_pipeline.generate_pixel_sheet") as generate,
        ):
            result = pipeline.generate_all("prompt", steps=["pixel"], skip_existing=True)

        assert result.skipped == ["pixel"]
        assert result.pixel_sheet_path == sheet
        generate.assert_not_called()

    def test_chibi_regeneration_forces_pixel_regeneration(self, tmp_path: Path) -> None:
        anima_dir = _anima_dir(tmp_path)
        assets = anima_dir / "assets"
        sheet = assets / "pixel_sheet.png"
        sheet.write_bytes(b"existing")
        pipeline = ImageGenPipeline(anima_dir, config=ImageGenConfig(image_style="anime"))

        reference_client = MagicMock()
        reference_client.generate_from_reference.return_value = b"new-chibi"

        with (
            patch("core.integrations._image_pipeline.codex_available", return_value=True),
            patch("core.integrations.image_gen._build_reference_client", return_value=reference_client),
            patch(
                "core.integrations._image_pipeline.generate_pixel_sheet",
                return_value=sheet,
            ) as generate,
        ):
            result = pipeline.generate_all(
                "prompt",
                steps=["chibi", "pixel"],
                skip_existing=True,
            )

        assert (assets / "avatar_chibi.png").read_bytes() == b"new-chibi"
        assert result.chibi_path == assets / "avatar_chibi.png"
        assert result.pixel_sheet_path == sheet
        generate.assert_called_once()

    def test_explicit_bustup_or_chibi_steps_add_pixel(self) -> None:
        from server.routes.assets import _normalize_asset_steps

        assert _normalize_asset_steps(["bustup"]) == ["bustup", "pixel"]
        assert _normalize_asset_steps(["chibi", "pixel"]) == ["chibi", "pixel"]
        assert _normalize_asset_steps(["pixel"]) == ["pixel"]
        assert _normalize_asset_steps(["fullbody"]) == ["fullbody"]
        assert _normalize_asset_steps(None) is None
