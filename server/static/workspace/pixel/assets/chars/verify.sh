#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
asset_dir="$(cd -- "${script_dir}/.." && pwd)"
generic_dir="${PIXEL_GENERIC_DIR:-${script_dir}}"
fleet_dir="${PIXEL_FLEET_DIR:-/tmp/pixel-fleet-assets/chars}"
polish_script="${script_dir}/build/pixel_polish.py"

python3 - "${asset_dir}/manifest.json" "${generic_dir}" "${fleet_dir}" "${polish_script}" <<'PY'
import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image

manifest_path = Path(sys.argv[1])
generic_dir = Path(sys.argv[2])
fleet_dir = Path(sys.argv[3])
polish_path = Path(sys.argv[4])

spec = importlib.util.spec_from_file_location("pixel_polish_verify", polish_path)
polish = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = polish
spec.loader.exec_module(polish)

generic_names = [
    *(f"sample_{index:02d}" for index in range(1, 7)),
    "human",
    "customer_a",
    "customer_b",
]
fleet_names = [
    "aoi",
    "ayame",
    "kotoha",
    "mei",
    "mio",
    "nagi",
    "natsume",
    "rin",
    "ritsu",
    "sakura",
    "sora",
    "sumire",
    "taka",
    "yoru",
]
rows = {
    "idle": 0,
    "working": 1,
    "thinking": 2,
    "talking": 3,
    "walk_down": 4,
    "walk_up": 5,
    "walk_side": 6,
    "sleeping": 7,
    "success": 8,
    "error": 9,
}
open_eye_rows = (0, 1, 2, 3, 4, 6, 8, 9)


def color_count(pixels, color):
    return sum(pixel == color for pixel in pixels)


def verify_face(frame, row, profile, label):
    if row == rows["walk_up"]:
        return
    center_y = polish.detect_face_y(frame, row, profile)
    face = [
        frame.getpixel((x, y))
        for y in range(max(0, center_y - 20), min(96, center_y + 23))
        for x in range(28, 69)
    ]
    mouth_pixels = color_count(face, profile["mouth"])
    if mouth_pixels < 12:
        raise SystemExit(f"{label}: mouth is not at least two pixels readable")

    if row in open_eye_rows:
        white_min = 30 if row == rows["walk_side"] else 55
        iris_min = 23 if row == rows["walk_side"] else 35
        glint_min = 1 if row == rows["walk_side"] else 2
        if color_count(face, profile["white"]) < white_min:
            raise SystemExit(f"{label}: sclera is too small")
        if color_count(face, profile["iris"]) < iris_min:
            raise SystemExit(f"{label}: iris is too small")
        if color_count(face, polish.EYE_GLINT) < glint_min:
            raise SystemExit(f"{label}: 1px eye highlight is missing")

    if row == rows["thinking"]:
        iris_y = [
            y
            for y in range(center_y - 10, center_y + 5)
            for x in range(34, 63)
            if frame.getpixel((x, y)) == profile["iris"]
        ]
        if not iris_y or max(iris_y) > center_y - 3:
            raise SystemExit(f"{label}: thinking gaze is not visibly raised")
    elif row == rows["sleeping"]:
        eye_band = [
            frame.getpixel((x, y))
            for y in range(center_y - 8, center_y + 4)
            for x in range(31, 66)
        ]
        if color_count(eye_band, profile["outline"]) < 80:
            raise SystemExit(f"{label}: sleeping chevron eyelids are missing")
        if color_count(eye_band, profile["white"]) > 8:
            raise SystemExit(f"{label}: sleeping eyes are not closed")
    elif row == rows["success"]:
        mouth_band = [
            frame.getpixel((x, y))
            for y in range(center_y + 5, center_y + 15)
            for x in range(37, 60)
        ]
        if color_count(mouth_band, profile["mouth"]) < 24:
            raise SystemExit(f"{label}: success smile is not visibly open")
    elif row == rows["error"]:
        panic_face = [
            frame.getpixel((x, y))
            for y in range(center_y - 16, center_y + 16)
            for x in range(31, 66)
        ]
        forehead = [
            frame.getpixel((x, y))
            for y in range(center_y - 17, center_y - 10)
            for x in range(42, 55)
        ]
        if color_count(panic_face, profile["panic"]) < 350:
            raise SystemExit(f"{label}: error face is not visibly blue")
        if color_count(panic_face, profile["white"]) < 60:
            raise SystemExit(f"{label}: error eyes are obscured")
        if color_count(panic_face, profile["iris"]) < 35:
            raise SystemExit(f"{label}: error irises are obscured")
        if color_count(panic_face, polish.THOUGHT_BLUE) < 8:
            raise SystemExit(f"{label}: error tear drops are missing")
        if color_count(forehead, profile["outline"]) < 25:
            raise SystemExit(f"{label}: error forehead stress lines are missing")

    if row in (rows["idle"], rows["working"]):
        brow_band = [
            frame.getpixel((x, y))
            for y in range(center_y - 13, center_y - 7)
            for x in range(33, 64)
        ]
        if color_count(brow_band, profile["outline"]) < 25:
            raise SystemExit(f"{label}: 1px eyebrows are missing")


def verify_sheet(path, *, limited_palette):
    if not path.is_file():
        raise SystemExit(f"missing sprite: {path}")
    image = Image.open(path).convert("RGBA")
    if image.size != (384, 960):
        raise SystemExit(f"{path.name}: expected 384x960, got {image.size}")
    alpha_values = {
        value for _, value in image.getchannel("A").getcolors(384 * 960)
    }
    if not alpha_values <= {0, 255}:
        raise SystemExit(f"{path.name}: soft alpha / antialiasing found")
    palette_size = len(image.getcolors(maxcolors=1_000_000) or [])
    if limited_palette and palette_size > 21:
        raise SystemExit(f"{path.name}: fleet palette expanded to {palette_size} colors")
    if not limited_palette and palette_size < 400:
        raise SystemExit(f"{path.name}: generic art appears bulk-posterized")

    profile = polish.sprite_profile(image)
    for row in range(10):
        for frame_index in range(4):
            frame = image.crop(
                (frame_index * 96, row * 96, (frame_index + 1) * 96, (row + 1) * 96)
            )
            verify_face(frame, row, profile, f"{path.name} row {row} frame {frame_index}")

    idle = image.crop((0, 0, 96, 96))
    idle_y = polish.detect_face_y(idle, rows["idle"], profile)
    excluded = {
        polish.TRANSPARENT,
        profile["outline"],
        profile["skin"],
        profile["mouth"],
        profile["white"],
        profile["iris"],
        profile["blush"],
        profile["panic"],
        polish.SKIN_SHADOW,
        polish.EYE_GLINT,
    }
    fringe_colors = {
        idle.getpixel((x, y))
        for y in range(idle_y - 15, idle_y - 5)
        for x in range(31, 66)
        if idle.getpixel((x, y))[3] and idle.getpixel((x, y)) not in excluded
    }
    luminance = [sum(color[:3]) for color in fringe_colors]
    if len(luminance) < 2 or max(luminance) - min(luminance) < 18:
        raise SystemExit(f"{path.name}: bright hair/face rim is missing")


manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
chars = manifest.get("chars", {})
if set(chars) != set(generic_names):
    raise SystemExit(f"manifest chars mismatch: {sorted(chars)}")
for name, config in chars.items():
    if config.get("file") != f"chars/{name}.png":
        raise SystemExit(f"{name}: invalid file")
    if (config.get("frameW"), config.get("frameH")) != (96, 96):
        raise SystemExit(f"{name}: invalid frame dimensions")
    animations = config.get("anims", {})
    if set(animations) != set(rows):
        raise SystemExit(f"{name}: invalid animation keys")
    for state, row in rows.items():
        if animations[state].get("row") != row or animations[state].get("frames") != 4:
            raise SystemExit(f"{name}.{state}: invalid row or frame count")

for name in generic_names:
    verify_sheet(generic_dir / f"{name}.png", limited_palette=False)
for name in fleet_names:
    verify_sheet(fleet_dir / f"{name}.png", limited_palette=True)

contacts = (
    (generic_dir / "_contact_sheet.png", (864, 336)),
    (fleet_dir / "_contact_sheet.png", (864, 560)),
)
for path, expected_size in contacts:
    if not path.is_file():
        raise SystemExit(f"missing contact sheet: {path}")
    actual_size = Image.open(path).size
    if actual_size != expected_size:
        raise SystemExit(f"{path}: expected {expected_size}, got {actual_size}")

print(
    "OK: verified 9 generic and 14 fleet sheets; "
    "idle/working brows and readable tearful blue error faces"
)
PY
