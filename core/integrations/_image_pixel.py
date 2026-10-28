# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Generate a Pixel Workspace character sheet from an approved base sheet.

Each of the ten animation rows is rendered independently by codex's built-in
``image_gen`` tool using the base row (nearest-neighbor enlarged and filled with
magenta) as the edit target.  The generated strip is chroma-keyed, each cell is
downscaled once into the base cell's occupied bounding box, and the ten rows are
assembled into a 256x640 RGBA sheet.
"""

from __future__ import annotations

import colorsys
import io
import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from PIL import Image

from core.integrations.image.codex import CodexImageClient
from core.integrations.image.prompts import (
    PIXEL_ROW_STATE_INSTRUCTIONS,
    PIXEL_ROW_STATES,
    build_pixel_row_prompt,
)

logger = logging.getLogger(__name__)

PIXEL_SHEET_FILENAME = "pixel_sheet.png"
PIXEL_FRAME_SIZE = 64
PIXEL_COLUMNS = 4
PIXEL_ROWS = 10
PIXEL_SHEET_SIZE = (PIXEL_FRAME_SIZE * PIXEL_COLUMNS, PIXEL_FRAME_SIZE * PIXEL_ROWS)

# Single source of truth for the bundled base sheet.  Cart replacements only
# need a 256x640 sheet at this path (or an ImageGenConfig.pixel_base_sheet).
_BUNDLED_PIXEL_BASE_SHEET = (
    Path(__file__).resolve().parents[2]
    / "server"
    / "static"
    / "workspace"
    / "pixel"
    / "assets"
    / "chars"
    / "sample_01.png"
)

_MAGENTA = (255, 0, 255)
_OPAQUE_THRESHOLD = 220
_TRANSPARENT_THRESHOLD = 12
_PARTIAL_ALPHA_LIMIT = 0.015
_MAX_ATTEMPTS = 2
# Seated rows must keep the face center within 1px so the character does not
# jitter at the desk; walking rows swing arms and legs, which moves the measured
# head run by a few pixels without any visible drift.
_WALK_ROWS = frozenset({4, 5, 6})
_WALK_CENTER_TOLERANCE = 3


class PixelSheetGenerationError(RuntimeError):
    """Raised when a pixel sheet cannot be generated or fails mechanical checks."""


def _resolve_base_sheet_path(config: Any = None) -> Path:
    configured = getattr(config, "pixel_base_sheet", None) if config is not None else None
    path = Path(configured).expanduser() if configured else _BUNDLED_PIXEL_BASE_SHEET
    if not path.is_file():
        raise PixelSheetGenerationError(f"Pixel base sheet not found: {path}")
    return path


def _load_base_sheet(config: Any = None) -> Image.Image:
    path = _resolve_base_sheet_path(config)
    try:
        with Image.open(path) as source:
            sheet = source.convert("RGBA")
    except Exception as exc:
        raise PixelSheetGenerationError(f"Failed to read pixel base sheet {path}: {exc}") from exc
    if sheet.size != PIXEL_SHEET_SIZE:
        raise PixelSheetGenerationError(
            f"Pixel base sheet must be {PIXEL_SHEET_SIZE[0]}x{PIXEL_SHEET_SIZE[1]}, got {sheet.width}x{sheet.height}: {path}"
        )
    return sheet


def extract_base_row(sheet: Image.Image, row_index: int) -> Image.Image:
    """Return the base row as a 256x64 RGBA strip."""
    top = row_index * PIXEL_FRAME_SIZE
    return sheet.crop((0, top, PIXEL_SHEET_SIZE[0], top + PIXEL_FRAME_SIZE)).convert("RGBA")


def build_magenta_base_row(base_row: Image.Image) -> bytes:
    """Enlarge a row 400% with nearest-neighbor sampling and fill transparency with magenta."""
    if base_row.size != (PIXEL_SHEET_SIZE[0], PIXEL_FRAME_SIZE):
        raise PixelSheetGenerationError(f"Base row must be 256x64, got {base_row.width}x{base_row.height}")
    enlarged = base_row.resize(
        (PIXEL_SHEET_SIZE[0] * 4, PIXEL_FRAME_SIZE * 4),
        Image.Resampling.NEAREST,
    )
    background = Image.new("RGB", enlarged.size, _MAGENTA)
    background.paste(enlarged, (0, 0), enlarged.getchannel("A"))
    buffer = io.BytesIO()
    background.save(buffer, format="PNG")
    return buffer.getvalue()


# ── Chroma-key removal ─────────────────────────────────────


def _is_magenta(pixel: tuple[int, int, int]) -> bool:
    r, g, b = pixel
    hue, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    degrees = hue * 360
    return 280 <= degrees <= 335 and saturation >= 0.45 and value >= 0.45


def extract_magenta_band(source: Image.Image) -> Image.Image:
    """Crop the contiguous band whose scan rows are mostly magenta."""
    image = source.convert("RGB")
    width, height = image.size
    pixels = image.load()
    band_rows: list[int] = []
    for y in range(height):
        magenta_count = sum(_is_magenta(pixels[x, y]) for x in range(width))
        if magenta_count >= width * 0.25:
            band_rows.append(y)
    if not band_rows:
        raise PixelSheetGenerationError("No magenta work area found in generated row")
    return image.crop((0, min(band_rows), width, max(band_rows) + 1))


def _border_key_color(image: Image.Image) -> tuple[int, int, int]:
    """Estimate the chroma key from the image border with a per-channel median."""
    image = image.convert("RGB")
    pixels = image.load()
    width, height = image.size
    values: list[tuple[int, int, int]] = []
    step_x = max(1, width // 64)
    step_y = max(1, height // 64)
    for x in range(0, width, step_x):
        values.append(pixels[x, 0])
        values.append(pixels[x, height - 1])
    for y in range(0, height, step_y):
        values.append(pixels[0, y])
        values.append(pixels[width - 1, y])
    if not values:
        return _MAGENTA
    ordered = sorted(values, key=lambda value: value[0] + value[1] + value[2])
    return ordered[len(ordered) // 2]


def _auto_key(image: Image.Image) -> Image.Image:
    """Approximate the imagegen soft-matte border key."""
    key = _border_key_color(image)
    source = image.convert("RGB")
    result = Image.new("RGBA", source.size)
    src = source.load()
    dst = result.load()
    for y in range(source.height):
        for x in range(source.width):
            r, g, b = src[x, y]
            distance = max(abs(r - key[0]), abs(g - key[1]), abs(b - key[2]))
            if distance <= _TRANSPARENT_THRESHOLD:
                alpha = 0
            elif distance >= _OPAQUE_THRESHOLD:
                alpha = 255
            else:
                alpha = round((distance - _TRANSPARENT_THRESHOLD) / (_OPAQUE_THRESHOLD - _TRANSPARENT_THRESHOLD) * 255)
            if max(r, g, b) <= 26:
                # Dark hair and suits must never disappear into the key.
                alpha = 255
            dst[x, y] = (r, g, b, alpha)
    return result


def _strict_magenta_key(image: Image.Image) -> Image.Image:
    """Remove only high-saturation magenta, preserving every dark color."""
    source = image.convert("RGB")
    result = Image.new("RGBA", source.size)
    src = source.load()
    dst = result.load()
    for y in range(source.height):
        for x in range(source.width):
            r, g, b = src[x, y]
            hue, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            degrees = hue * 360
            if value <= 0.10:
                dst[x, y] = (r, g, b, 255)
            elif saturation >= 0.45 and 280 <= degrees <= 335 and value >= 0.45:
                dst[x, y] = (0, 0, 0, 0)
            else:
                dst[x, y] = (r, g, b, 255)
    return result


def _finalize_alpha(image: Image.Image) -> Image.Image:
    """Neutralize near-black tinted edges and make alpha binary."""
    source = image.convert("RGBA")
    pixels = source.load()
    for y in range(source.height):
        for x in range(source.width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                pixels[x, y] = (0, 0, 0, 0)
                continue
            hue, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            degrees = hue * 360
            if value <= 0.10 and saturation >= 0.50 and (70 <= degrees <= 170 or 280 <= degrees <= 330):
                # BOX resampling can tint near-black edges by a few RGB levels.
                # Keep their opacity but remove the meaningless hue so a dark
                # character is not mistaken for leftover chroma.
                neutral = max(r, g, b)
                pixels[x, y] = (neutral, neutral, neutral, 255)
            else:
                pixels[x, y] = (r, g, b, 255 if a >= 128 else 0)
    return source


def remove_chroma_key(image: Image.Image) -> Image.Image:
    """Remove the magenta background using the SKILL.md dark-color guards."""
    keyed = _auto_key(image)
    alpha_values = keyed.getchannel("A").tobytes()
    partial_ratio = sum(0 < value < 255 for value in alpha_values) / len(alpha_values)
    if partial_ratio > _PARTIAL_ALPHA_LIMIT:
        # Dusty pink/beige character colors can be close enough to magenta for
        # the soft matte to make the subject translucent.  Fall back to strict
        # HSV magenta removal, which never touches near-black pixels.
        logger.debug("Pixel row soft matte partial alpha %.1f%%; using strict HSV key", partial_ratio * 100)
        keyed = _strict_magenta_key(image)
    return _finalize_alpha(keyed)


# ── Cell normalization and mechanical checks ───────────────


def _head_metrics(image: Image.Image, band: int = 40) -> tuple[int, int, int] | None:
    """Return (head top y, head width, head center x) for the upper part of a frame."""
    alpha = image.getchannel("A")
    bbox = alpha.point(lambda value: 255 if value > 10 else 0).getbbox()
    if bbox is None:
        return None
    top = bbox[1]
    center = image.width // 2
    best_width = 0
    best_center = center
    pixels = alpha.load()
    for y in range(top, min(top + band, image.height)):
        xs = [x for x in range(image.width) if pixels[x, y] > 10]
        if not xs:
            continue
        runs: list[tuple[int, int]] = []
        start = xs[0]
        for previous, current in zip(xs, xs[1:], strict=False):
            if current != previous + 1:
                runs.append((start, previous))
                start = current
        runs.append((start, xs[-1]))
        # Measure the run nearest the frame center so detached arms or props do
        # not widen the head and pull the face-center alignment off target.
        run = min(runs, key=lambda item: abs((item[0] + item[1]) / 2 - center))
        width = run[1] - run[0] + 1
        if width > best_width:
            best_width = width
            best_center = (run[0] + run[1] + 1) // 2
    return top, best_width, best_center


def _occupied_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    return image.getchannel("A").point(lambda value: 255 if value >= 128 else 0).getbbox()


def _drop_line_artifacts(cell: Image.Image) -> Image.Image:
    """Clear detached thin vertical strokes (panel borders the model sometimes draws).

    A component counts as an artifact when it is at most 1/16 of the cell wide
    and spans at least 40% of its height; sparkles and sweat drops stay because
    they are short.
    """
    width, height = cell.size
    alpha = cell.getchannel("A").load()
    seen = bytearray(width * height)
    max_width = max(2, width // 16)
    min_height = height * 0.4
    cleaned: Image.Image | None = None
    for start_y in range(height):
        for start_x in range(width):
            index = start_y * width + start_x
            if seen[index] or alpha[start_x, start_y] < 128:
                continue
            seen[index] = 1
            stack = [(start_x, start_y)]
            component: list[tuple[int, int]] = []
            min_x = max_x = start_x
            min_y = max_y = start_y
            while stack:
                x, y = stack.pop()
                component.append((x, y))
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < width and 0 <= ny < height:
                        neighbor = ny * width + nx
                        if not seen[neighbor] and alpha[nx, ny] >= 128:
                            seen[neighbor] = 1
                            stack.append((nx, ny))
            if max_x - min_x + 1 <= max_width and max_y - min_y + 1 >= min_height:
                if cleaned is None:
                    cleaned = cell.copy()
                pixels = cleaned.load()
                for x, y in component:
                    pixels[x, y] = (0, 0, 0, 0)
    return cleaned if cleaned is not None else cell


def _shift_frame_x(frame: Image.Image, offset: int) -> Image.Image:
    if not offset:
        return frame
    shifted = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    shifted.paste(frame, (offset, 0))
    return shifted


def _normalize_cells(keyed: Image.Image, base_row: Image.Image, row_index: int) -> Image.Image:
    """Scale each generated cell once into the base cell bbox and place it there."""
    width, height = keyed.size
    output = Image.new("RGBA", (PIXEL_SHEET_SIZE[0], PIXEL_FRAME_SIZE), (0, 0, 0, 0))
    frame_width = width / PIXEL_COLUMNS
    for column in range(PIXEL_COLUMNS):
        generated_left = round(column * frame_width)
        generated_right = round((column + 1) * frame_width)
        generated_cell = _drop_line_artifacts(keyed.crop((generated_left, 0, generated_right, height)))
        generated_bbox = _occupied_bbox(generated_cell)
        if generated_bbox is None:
            raise PixelSheetGenerationError(f"Row {row_index} frame {column} is empty after chroma-key removal")

        reference_left = column * PIXEL_FRAME_SIZE
        reference_cell = base_row.crop((reference_left, 0, reference_left + PIXEL_FRAME_SIZE, PIXEL_FRAME_SIZE))
        reference_bbox = _occupied_bbox(reference_cell)
        if reference_bbox is None:
            raise PixelSheetGenerationError(f"Base row {row_index} frame {column} is empty")

        sprite = generated_cell.crop(generated_bbox).resize(
            (reference_bbox[2] - reference_bbox[0], reference_bbox[3] - reference_bbox[1]),
            Image.Resampling.BOX,
        )
        frame = Image.new("RGBA", (PIXEL_FRAME_SIZE, PIXEL_FRAME_SIZE), (0, 0, 0, 0))
        frame.paste(sprite, (reference_bbox[0], reference_bbox[1]))

        generated_head = _head_metrics(frame)
        reference_head = _head_metrics(reference_cell)
        if generated_head is not None and reference_head is not None:
            offset = round(reference_head[2] - generated_head[2])
            frame = _shift_frame_x(frame, offset)

        output.paste(_finalize_alpha(frame), (reference_left, 0))
    return output


def process_generated_row(raw_bytes: bytes, base_row: Image.Image, row_index: int) -> Image.Image:
    """Convert one raw codex strip into a normalized 256x64 RGBA row."""
    try:
        with Image.open(io.BytesIO(raw_bytes)) as source:
            generated = source.convert("RGB")
    except Exception as exc:
        raise PixelSheetGenerationError(f"Generated row {row_index} is not a readable image: {exc}") from exc
    band = extract_magenta_band(generated)
    keyed = remove_chroma_key(band)
    return _normalize_cells(keyed, base_row, row_index)


def check_pixel_row(row: Image.Image, base_row: Image.Image, row_index: int) -> None:
    """Raise when a processed row deviates from the base row's geometry."""
    if row.size != (PIXEL_SHEET_SIZE[0], PIXEL_FRAME_SIZE):
        raise PixelSheetGenerationError(f"Row {row_index} must be 256x64, got {row.width}x{row.height}")
    alpha = row.getchannel("A")
    if any(value not in (0, 255) for value in alpha.tobytes()):
        raise PixelSheetGenerationError(f"Row {row_index} alpha is not binary")

    generated_total = 0
    reference_total = 0
    for column in range(PIXEL_COLUMNS):
        left = column * PIXEL_FRAME_SIZE
        generated_cell = row.crop((left, 0, left + PIXEL_FRAME_SIZE, PIXEL_FRAME_SIZE))
        reference_cell = base_row.crop((left, 0, left + PIXEL_FRAME_SIZE, PIXEL_FRAME_SIZE))
        generated_bbox = _occupied_bbox(generated_cell)
        reference_bbox = _occupied_bbox(reference_cell)
        if generated_bbox is None:
            raise PixelSheetGenerationError(f"Row {row_index} frame {column} is empty")
        if reference_bbox is None:
            raise PixelSheetGenerationError(f"Base row {row_index} frame {column} is empty")
        if abs(generated_bbox[1] - reference_bbox[1]) > 1:
            raise PixelSheetGenerationError(
                f"Row {row_index} frame {column} head top {generated_bbox[1]} differs from base {reference_bbox[1]}"
            )
        generated_head = _head_metrics(generated_cell)
        reference_head = _head_metrics(reference_cell)
        if generated_head is None or reference_head is None:
            raise PixelSheetGenerationError(f"Row {row_index} frame {column} head cannot be measured")
        center_tolerance = _WALK_CENTER_TOLERANCE if row_index in _WALK_ROWS else 1
        if abs(generated_head[2] - reference_head[2]) > center_tolerance:
            raise PixelSheetGenerationError(
                f"Row {row_index} frame {column} face center {generated_head[2]} differs from base {reference_head[2]}"
            )
        generated_total += sum(1 for value in generated_cell.getchannel("A").tobytes() if value)
        reference_total += sum(1 for value in reference_cell.getchannel("A").tobytes() if value)

    if reference_total == 0:
        raise PixelSheetGenerationError(f"Base row {row_index} has no opaque pixels")
    ratio = generated_total / reference_total
    if not 0.75 <= ratio <= 1.35:
        raise PixelSheetGenerationError(f"Row {row_index} area ratio {ratio:.2f} is outside 0.75-1.35")


# ── Generation ─────────────────────────────────────────────


def _build_pixel_row_spec(prompt: str) -> str:
    lines = [
        "# Image generation spec",
        "",
        "## Tool",
        "Use the built-in `image_gen` tool. Substituting SVG/HTML/CSS or hand-drawn scripts is not acceptable.",
        (
            "After generating, call `view_image` to inspect your own output. If the face has black blobs, "
            "stray dark pixels, or dirt, regenerate the image before saving it."
        ),
        "",
        "## Subject",
        prompt,
        "",
        "## Output contract",
        (
            "Save the final image as a PNG named `out.png` in the current directory, then finish. "
            "Do not create any other files."
        ),
        "",
    ]
    return "\n".join(lines)


def _identity_description(anima_dir: Path, prompt: str) -> str:
    prompt_file = anima_dir / "assets" / "prompt.txt"
    if prompt_file.is_file():
        try:
            cached = prompt_file.read_text(encoding="utf-8").strip()
        except OSError:
            cached = ""
        if cached:
            return cached
    fallback = (prompt or "").strip()
    if not fallback:
        raise PixelSheetGenerationError("No identity prompt available for pixel sheet generation")
    return fallback


def _reference_images(anima_dir: Path, config: Any) -> list[bytes]:
    assets_dir = anima_dir / "assets"
    realistic = getattr(config, "image_style", "anime") == "realistic"
    suffix = "_realistic" if realistic else ""
    fullbody = assets_dir / f"avatar_fullbody{suffix}.png"
    chibi = assets_dir / "avatar_chibi.png"
    bustup = assets_dir / f"avatar_bustup{suffix}.png"

    second = chibi if chibi.is_file() else fullbody
    candidates = [second, bustup]
    references: list[bytes] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen or not candidate.is_file():
            continue
        try:
            references.append(candidate.read_bytes())
            seen.add(candidate)
        except OSError as exc:
            raise PixelSheetGenerationError(f"Failed to read pixel reference image {candidate}: {exc}") from exc
    if not references:
        raise PixelSheetGenerationError("No identity reference image available for pixel sheet generation")
    return references


def _render_row(
    row_index: int,
    state: str,
    base_row: Image.Image,
    magenta_base: bytes,
    references: list[bytes],
    config: Any,
    identity: str,
    anchor: bytes | None = None,
) -> Image.Image:
    prompt = build_pixel_row_prompt(
        state=state,
        state_instructions=PIXEL_ROW_STATE_INSTRUCTIONS[state],
        identity=identity,
        image_count=len(references) + 1,
        has_anchor=anchor is not None,
    )
    spec = _build_pixel_row_spec(prompt)
    client = CodexImageClient(config)
    last_error: PixelSheetGenerationError | None = None
    for attempt in range(_MAX_ATTEMPTS):
        images = [magenta_base, *references]
        if anchor is not None:
            images.append(anchor)
        raw = client.generate_pixel_row(spec, images)
        try:
            row = process_generated_row(raw, base_row, row_index)
            check_pixel_row(row, base_row, row_index)
            return row
        except PixelSheetGenerationError as exc:
            last_error = exc
            logger.warning(
                "Pixel row %d (%s) failed mechanical inspection (attempt %d/%d): %s",
                row_index,
                state,
                attempt + 1,
                _MAX_ATTEMPTS,
                exc,
            )
    raise PixelSheetGenerationError(
        f"Pixel row {row_index} ({state}) failed after {_MAX_ATTEMPTS} attempts: {last_error}"
    )


def generate_pixel_sheet(
    anima_dir: Path,
    config: Any,
    prompt: str,
    progress_callback: Callable[[str, str, int], None] | None = None,
) -> Path:
    """Generate ``assets/pixel_sheet.png`` and return its path.

    Raises :class:`PixelSheetGenerationError` when any row cannot pass the
    mechanical inspection after one regeneration; no partial sheet is written.
    """
    base_sheet = _load_base_sheet(config)
    references = _reference_images(anima_dir, config)
    identity = _identity_description(anima_dir, prompt)

    def notify(status: str, pct: int = 0) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback("pixel", status, pct)
        except Exception:
            logger.debug("pixel progress_callback error (ignored)", exc_info=True)

    rows = [(index, state) for index, state in enumerate(PIXEL_ROW_STATES)]
    base_rows = {index: extract_base_row(base_sheet, index) for index, _ in rows}
    magenta_bases = {index: build_magenta_base_row(base_rows[index]) for index, _ in rows}
    workers = max(1, int(getattr(config, "pixel_concurrency", 4) or 1))
    logger.info(
        "Generating pixel sheet for %s: %d rows, %d worker(s)",
        anima_dir,
        len(rows),
        workers,
    )
    notify("generating", 0)

    # Rows rendered independently drift in hair color and length, so the idle row
    # is rendered first and handed to every other row as the identity anchor.
    anchor_index, anchor_state = rows[0]
    results: dict[int, Image.Image] = {
        anchor_index: _render_row(
            anchor_index,
            anchor_state,
            base_rows[anchor_index],
            magenta_bases[anchor_index],
            references,
            config,
            identity,
        )
    }
    anchor = build_magenta_base_row(results[anchor_index])
    completed = 1
    notify("generating", round(completed * 100 / len(rows)))
    completed_lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _render_row,
                index,
                state,
                base_rows[index],
                magenta_bases[index],
                references,
                config,
                identity,
                anchor,
            ): index
            for index, state in rows[1:]
        }
        try:
            for future in as_completed(futures):
                index = futures[future]
                results[index] = future.result()
                with completed_lock:
                    completed += 1
                    pct = round(completed * 100 / len(rows))
                notify("generating", pct)
        except Exception:
            for future in futures:
                future.cancel()
            raise

    sheet = Image.new("RGBA", PIXEL_SHEET_SIZE, (0, 0, 0, 0))
    for index, _ in rows:
        sheet.alpha_composite(results[index], (0, index * PIXEL_FRAME_SIZE))

    assets_dir = anima_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    output_path = assets_dir / PIXEL_SHEET_FILENAME
    temp_path = assets_dir / f".{PIXEL_SHEET_FILENAME}.tmp-{os.getpid()}-{threading.get_ident()}"
    try:
        sheet.save(temp_path, format="PNG")
        temp_path.replace(output_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    notify("completed", 100)
    logger.info("Pixel sheet saved: %s", output_path)
    return output_path
