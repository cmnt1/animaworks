#!/usr/bin/env python3
"""Convert one built-in imagegen strip into the required 384x96 RGBA row.

The image model emits a 3:1 canvas even though the source strip is 4:1.  This
script extracts the magenta work area, removes that key with the installed
imagegen helper, then downsamples each of the four generated cells into the
corresponding reference frame's occupied bounding box.
"""

from __future__ import annotations

import argparse
import colorsys
import subprocess
import sys
from pathlib import Path

from PIL import Image


KEY_HELPER = Path(
    "~/.codex/skills/.system/imagegen/scripts/remove_chroma_key.py"
).expanduser()


def is_magenta(pixel: tuple[int, int, int]) -> bool:
    r, g, b = pixel
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    degrees = h * 360
    return 280 <= degrees <= 335 and s >= 0.45 and v >= 0.45


def extract_magenta_band(source: Path, output: Path) -> None:
    image = Image.open(source).convert("RGB")
    width, height = image.size
    pixels = image.load()
    rows: list[int] = []
    for y in range(height):
        magenta_count = sum(is_magenta(pixels[x, y]) for x in range(width))
        if magenta_count >= width * 0.25:
            rows.append(y)
    if not rows:
        raise RuntimeError(f"No magenta work area found in {source}")
    top, bottom = min(rows), max(rows) + 1
    image.crop((0, top, width, bottom)).save(output)


def binary_alpha(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            r, g, b, a = pixels[x, y]
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            degrees = h * 360
            # The built-in model sometimes adds subtle variation to the flat
            # key.  Remove the exact forbidden magenta range before making
            # alpha binary so it cannot inflate the occupied bounding box.
            if (
                a
                and v <= 0.10
                and s >= 0.50
                and (70 <= degrees <= 170 or 280 <= degrees <= 330)
            ):
                # BOX resampling can tint near-black edge pixels by a few RGB
                # levels.  Preserve their opacity/geometry but remove the
                # meaningless hue so the strict residue check stays clean.
                neutral = max(r, g, b)
                pixels[x, y] = (
                    neutral,
                    neutral,
                    neutral,
                    255 if a >= 128 else 0,
                )
            elif a and s >= 0.45 and 280 <= degrees <= 330:
                pixels[x, y] = (0, 0, 0, 0)
            else:
                pixels[x, y] = (r, g, b, 255 if a >= 128 else 0)
    return rgba


def occupied_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    bbox = image.getchannel("A").point(lambda value: 255 if value >= 128 else 0).getbbox()
    if bbox is None:
        raise RuntimeError("Generated frame is empty after chroma-key removal")
    return bbox


def head_metrics(image: Image.Image, band: int = 40) -> tuple[int, int, float]:
    alpha = image.getchannel("A")
    bbox = alpha.point(lambda value: 255 if value > 10 else 0).getbbox()
    if bbox is None:
        raise RuntimeError("Cannot measure head in empty frame")
    top = bbox[1]
    center = image.width // 2
    best_width, best_center = 0, float(center)
    pixels = alpha.load()
    for y in range(top, min(top + band, image.height)):
        xs = [x for x in range(image.width) if pixels[x, y] > 10]
        if not xs:
            continue
        runs: list[tuple[int, int]] = []
        start = xs[0]
        for previous, current in zip(xs, xs[1:]):
            if current != previous + 1:
                runs.append((start, previous))
                start = current
        runs.append((start, xs[-1]))
        run = min(runs, key=lambda item: abs((item[0] + item[1]) / 2 - center))
        width = run[1] - run[0] + 1
        if width > best_width:
            best_width = width
            best_center = (run[0] + run[1] + 1) / 2
    return top, best_width, best_center


def translate_x(image: Image.Image, offset: int) -> Image.Image:
    if offset == 0:
        return image
    shifted = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shifted.alpha_composite(image, (offset, 0))
    return binary_alpha(shifted)


def constrain_head_geometry(
    frame: Image.Image, reference: Image.Image, head_tolerance: int = 10
) -> Image.Image:
    _, _, target_center = head_metrics(frame)
    _, reference_width, reference_center = head_metrics(reference)
    offset = round(reference_center - target_center)
    frame = translate_x(frame, offset)

    max_width = reference_width + head_tolerance
    top, _, _ = head_metrics(frame)
    pixels = frame.load()
    alpha = frame.getchannel("A")
    alpha_pixels = alpha.load()
    center = frame.width // 2
    for y in range(top, min(top + 40, frame.height)):
        xs = [x for x in range(frame.width) if alpha_pixels[x, y] > 10]
        if not xs:
            continue
        runs: list[tuple[int, int]] = []
        start = xs[0]
        for previous, current in zip(xs, xs[1:]):
            if current != previous + 1:
                runs.append((start, previous))
                start = current
        runs.append((start, xs[-1]))
        left, right = min(
            runs, key=lambda item: abs((item[0] + item[1]) / 2 - center)
        )
        excess = right - left + 1 - max_width
        while excess > 0:
            # Remove symmetric outer pixels first.  For an odd excess, remove
            # from the side farther from the reference head center.
            if excess >= 2:
                pixels[left, y] = (0, 0, 0, 0)
                pixels[right, y] = (0, 0, 0, 0)
                left += 1
                right -= 1
                excess -= 2
            elif (left + right + 1) / 2 < reference_center:
                pixels[left, y] = (0, 0, 0, 0)
                excess -= 1
            else:
                pixels[right, y] = (0, 0, 0, 0)
                excess -= 1
    return binary_alpha(frame)


def normalize_cells(keyed_path: Path, reference_path: Path, output_path: Path) -> None:
    keyed = binary_alpha(Image.open(keyed_path))
    reference = Image.open(reference_path).convert("RGBA")
    if reference.size != (384, 96):
        raise RuntimeError(f"Reference row must be 384x96, got {reference.size}")

    frames: list[Image.Image] = []
    for column in range(4):
        left = round(column * keyed.width / 4)
        right = round((column + 1) * keyed.width / 4)
        generated_cell = keyed.crop((left, 0, right, keyed.height))
        generated_bbox = occupied_bbox(generated_cell)
        generated_sprite = generated_cell.crop(generated_bbox)

        reference_cell = reference.crop((column * 96, 0, (column + 1) * 96, 96))
        ref_left, ref_top, ref_right, ref_bottom = occupied_bbox(reference_cell)
        ref_width, ref_height = ref_right - ref_left, ref_bottom - ref_top

        generated_sprite = generated_sprite.resize(
            (ref_width, ref_height), resample=Image.Resampling.BOX
        )
        generated_sprite = binary_alpha(generated_sprite)
        frame = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
        frame.alpha_composite(generated_sprite, (ref_left, ref_top))
        frame = binary_alpha(frame)
        frame = constrain_head_geometry(frame, reference_cell)
        frames.append(frame)

    strip = Image.new("RGBA", (384, 96), (0, 0, 0, 0))
    for column, frame in enumerate(frames):
        strip.alpha_composite(frame, (column * 96, 0))
    strip = binary_alpha(strip)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    strip.save(output_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()

    args.work_dir.mkdir(parents=True, exist_ok=True)
    band_path = args.work_dir / f"{args.output.stem}_band.png"
    keyed_path = args.work_dir / f"{args.output.stem}_keyed.png"

    extract_magenta_band(args.source, band_path)
    subprocess.run(
        [
            sys.executable,
            str(KEY_HELPER),
            "--input",
            str(band_path),
            "--out",
            str(keyed_path),
            "--auto-key",
            "border",
            "--soft-matte",
            "--transparent-threshold",
            "12",
            "--opaque-threshold",
            "220",
            "--despill",
        ],
        check=True,
    )
    keyed_image = Image.open(keyed_path).convert("RGBA")
    alpha_values = list(keyed_image.getchannel("A").getdata())
    partial_count = sum(0 < value < 255 for value in alpha_values)
    partial_ratio = partial_count / len(alpha_values)
    normalization_source = keyed_path
    if partial_ratio > 0.015:
        # Dusty pink/beige character colors can be close enough to magenta for
        # the soft-matte helper to make the subject translucent.  In that
        # failure mode, retain the original RGB band and remove only the
        # explicitly forbidden high-saturation magenta range in binary_alpha.
        print(
            f"Soft-matte partial alpha ratio {partial_ratio:.1%}; "
            "using strict HSV magenta fallback"
        )
        normalization_source = band_path
    normalize_cells(normalization_source, args.reference, args.output)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
