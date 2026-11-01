"""Unit tests for core.integrations._image_pixel."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw

from core.config.models import ImageGenConfig
from core.integrations import _image_pixel

MAGENTA = (255, 0, 255)


def _make_base_sheet() -> Image.Image:
    sheet = Image.new("RGBA", (256, 640), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    for row in range(10):
        top = row * 64
        for column in range(4):
            left = column * 64
            draw.rectangle(
                [left + 8, top + 8, left + 39, top + 63],
                fill=(40, 40, 48, 255),
            )
            draw.rectangle(
                [left + 14, top + 14, left + 29, top + 27],
                fill=(240, 210, 190, 255),
            )
    return sheet


def _base_sheet_path(tmp_path: Path) -> Path:
    path = tmp_path / "base.png"
    _make_base_sheet().save(path)
    return path


def _generated_row_bytes() -> bytes:
    image = Image.new("RGB", (1024, 256), MAGENTA)
    draw = ImageDraw.Draw(image)
    for column in range(4):
        left = column * 256 + 16
        draw.rectangle([left, 32, left + 31, 87], fill=(17, 17, 17))
        draw.rectangle([left + 6, 38, left + 21, 51], fill=(240, 210, 190))
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _shift_down(row: Image.Image, pixels: int = 2) -> Image.Image:
    shifted = Image.new("RGBA", row.size, (0, 0, 0, 0))
    shifted.paste(row, (0, pixels))
    return shifted


def _write_anima_assets(anima_dir: Path) -> None:
    assets = anima_dir / "assets"
    assets.mkdir(parents=True)
    (assets / "prompt.txt").write_text("short black hair, red jacket", encoding="utf-8")
    reference = Image.new("RGBA", (64, 64), (240, 210, 190, 255))
    reference.save(assets / "avatar_chibi.png")


class TestPostprocess:
    def test_magenta_key_preserves_dark_hair_and_binary_alpha(self) -> None:
        row = _image_pixel.process_generated_row(_generated_row_bytes(), _make_base_sheet().crop((0, 0, 256, 64)), 0)

        assert row.size == (256, 64)
        assert set(row.getchannel("A").tobytes()) <= {0, 255}
        # The dark block must survive the chroma key (near-black is never transparent).
        assert row.getpixel((10, 10))[3] == 255
        assert row.getpixel((34, 60))[3] == 255
        # Background pixels are fully transparent.
        assert row.getpixel((0, 0))[3] == 0

    def test_strict_magenta_fallback_keeps_dark_pixels(self) -> None:
        image = Image.new("RGB", (32, 32), MAGENTA)
        draw = ImageDraw.Draw(image)
        draw.rectangle([8, 8, 20, 24], fill=(8, 8, 8))
        raw = Image.new("RGBA", image.size, (0, 0, 0, 0))
        raw.paste(image)

        keyed = _image_pixel._strict_magenta_key(image)
        finalized = _image_pixel._finalize_alpha(keyed)

        assert finalized.getpixel((12, 12))[3] == 255
        assert finalized.getpixel((0, 0))[3] == 0


class TestRowInspection:
    def test_head_top_mismatch_is_rejected(self) -> None:
        base_row = _make_base_sheet().crop((0, 0, 256, 64))
        shifted = _shift_down(base_row)

        with pytest.raises(_image_pixel.PixelSheetGenerationError, match="head top"):
            _image_pixel.check_pixel_row(shifted, base_row, 0)

    @pytest.mark.parametrize(("row_index", "rejected"), [(0, True), (6, False)])
    def test_face_center_tolerance_is_looser_for_walk_rows(self, row_index: int, rejected: bool) -> None:
        base_row = _make_base_sheet().crop((0, 0, 256, 64))
        moved = Image.new("RGBA", base_row.size, (0, 0, 0, 0))
        moved.paste(base_row, (2, 0))

        if rejected:
            with pytest.raises(_image_pixel.PixelSheetGenerationError, match="face center"):
                _image_pixel.check_pixel_row(moved, base_row, row_index)
        else:
            _image_pixel.check_pixel_row(moved, base_row, row_index)

    def test_failed_row_regenerates_exactly_once(self) -> None:
        base_row = _make_base_sheet().crop((0, 0, 256, 64))
        config = ImageGenConfig(image_style="anime")

        def shifted_process(raw: bytes, base: Image.Image, row_index: int) -> Image.Image:
            return _shift_down(base)

        with (
            patch.object(
                _image_pixel.CodexImageClient,
                "generate_pixel_row",
                return_value=b"raw",
            ) as generate,
            patch.object(_image_pixel, "process_generated_row", side_effect=shifted_process),
            pytest.raises(_image_pixel.PixelSheetGenerationError, match="failed after 2 attempts"),
        ):
            _image_pixel._render_row(
                0,
                "idle",
                base_row,
                b"magenta-base",
                [b"reference"],
                config,
                "short black hair",
            )

        assert generate.call_count == 2

    def test_failed_generation_does_not_write_a_partial_sheet(self, tmp_path: Path) -> None:
        anima_dir = tmp_path / "anima"
        _write_anima_assets(anima_dir)
        base_path = _base_sheet_path(tmp_path)
        config = ImageGenConfig(
            image_style="anime",
            pixel_base_sheet=str(base_path),
            pixel_concurrency=1,
        )

        def shifted_process(raw: bytes, base: Image.Image, row_index: int) -> Image.Image:
            return _shift_down(base)

        with (
            patch.object(
                _image_pixel.CodexImageClient,
                "generate_pixel_row",
                return_value=b"raw",
            ) as generate,
            patch.object(_image_pixel, "process_generated_row", side_effect=shifted_process),
            pytest.raises(_image_pixel.PixelSheetGenerationError, match="failed after 2 attempts"),
        ):
            _image_pixel.generate_pixel_sheet(anima_dir, config, "prompt")

        assert generate.call_count >= 2
        assert generate.call_count <= 20
        assert not (anima_dir / "assets" / _image_pixel.PIXEL_SHEET_FILENAME).exists()

    def test_successful_sheet_is_256x640_and_atomic(self, tmp_path: Path) -> None:
        anima_dir = tmp_path / "anima"
        _write_anima_assets(anima_dir)
        base_path = _base_sheet_path(tmp_path)
        config = ImageGenConfig(
            image_style="anime",
            pixel_base_sheet=str(base_path),
            pixel_concurrency=2,
        )

        with patch.object(
            _image_pixel.CodexImageClient,
            "generate_pixel_row",
            return_value=_generated_row_bytes(),
        ) as generate:
            output = _image_pixel.generate_pixel_sheet(anima_dir, config, "prompt")

        assert generate.call_count == 10
        assert output == anima_dir / "assets" / "pixel_sheet.png"
        assert output.exists()
        with Image.open(output) as sheet:
            assert sheet.size == (256, 640)
            assert sheet.mode == "RGBA"
            assert set(sheet.getchannel("A").tobytes()) <= {0, 255}
            # The synthetic dark block survives on every row.
            assert sheet.getpixel((10, 10))[3] == 255
        assert not list((anima_dir / "assets").glob(".pixel_sheet.png.tmp-*"))

    def test_idle_row_is_passed_as_anchor_to_other_rows(self, tmp_path: Path) -> None:
        anima_dir = tmp_path / "anima"
        _write_anima_assets(anima_dir)
        config = ImageGenConfig(
            image_style="anime",
            pixel_base_sheet=str(_base_sheet_path(tmp_path)),
            pixel_concurrency=3,
        )

        with patch.object(
            _image_pixel.CodexImageClient,
            "generate_pixel_row",
            return_value=_generated_row_bytes(),
        ) as generate:
            _image_pixel.generate_pixel_sheet(anima_dir, config, "prompt")

        calls = generate.call_args_list
        first_spec, first_images = calls[0].args
        assert "finished idle row" not in first_spec
        assert len(first_images) == 2  # base row + chibi
        for call in calls[1:]:
            spec, images = call.args
            assert "Image 3 is the already finished idle row" in spec
            assert len(images) == 3


class TestLineArtifacts:
    def test_detached_vertical_stroke_is_removed(self) -> None:
        cell = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        draw = ImageDraw.Draw(cell)
        draw.rectangle([40, 30, 140, 250], fill=(30, 30, 30, 255))  # body
        draw.rectangle([240, 0, 243, 255], fill=(90, 90, 90, 255))  # panel border
        draw.rectangle([200, 40, 208, 50], fill=(255, 220, 0, 255))  # sparkle

        cleaned = _image_pixel._drop_line_artifacts(cell)

        assert cleaned.getpixel((241, 100))[3] == 0
        assert cleaned.getpixel((90, 100))[3] == 255
        assert cleaned.getpixel((204, 45))[3] == 255
