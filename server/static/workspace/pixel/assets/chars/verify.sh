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


def color_components(frame, colors):
    points = {
        (x, y)
        for y in range(8, 88)
        for x in range(26, 70)
        if frame.getpixel((x, y)) in colors
    }
    components = []
    while points:
        queue = [points.pop()]
        component = []
        while queue:
            x, y = queue.pop()
            component.append((x, y))
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in points:
                    points.remove(neighbor)
                    queue.append(neighbor)
        if len(component) >= 8:
            components.append(component)
    return components


def verify_living_eye(frame, expected_x, profile, label):
    iris_colors = {profile["iris"], profile["iris_light"]}
    components = color_components(frame, iris_colors)
    candidates = [
        component
        for component in components
        if abs(sum(x for x, _ in component) / len(component) - expected_x) <= 5
    ]
    if not candidates:
        raise SystemExit(f"{label}: character-colored iris is missing at x={expected_x}")
    component = max(candidates, key=len)
    xs = [x for x, _ in component]
    ys = [y for _, y in component]
    center_x = round(sum(xs) / len(xs))
    iris_top = min(ys)
    region_points = [
        (x, y)
        for y in range(iris_top - 3, iris_top + 10)
        for x in range(center_x - 5, center_x + 6)
    ]
    pixels = [frame.getpixel(point) for point in region_points]
    visible = [
        point
        for point in region_points
        if frame.getpixel(point)
        in {profile["white"], profile["iris"], profile["iris_light"], polish.EYE_GLINT}
    ]
    width = max(x for x, _ in visible) - min(x for x, _ in visible) + 1
    height = max(y for _, y in visible) - min(y for _, y in visible) + 1
    if width < 5 or height < 6:
        raise SystemExit(f"{label}: eye is only {width}x{height}, expected at least 5x6")
    if color_count(pixels, profile["white"]) < 24:
        raise SystemExit(f"{label}: open sclera is too small")
    if color_count(pixels, profile["iris"]) < 12:
        raise SystemExit(f"{label}: primary iris tier is missing")
    if color_count(pixels, profile["iris_light"]) < 3:
        raise SystemExit(f"{label}: secondary iris tier is missing")
    if color_count(pixels, polish.EYE_GLINT) != 1:
        raise SystemExit(f"{label}: expected exactly one white iris highlight")
    lash = max(
        sum(
            frame.getpixel((x, y)) == profile["outline"]
            for x in range(center_x - 5, center_x + 6)
        )
        for y in range(iris_top - 3, iris_top + 3)
    )
    if lash < 4:
        raise SystemExit(f"{label}: 1px upper lash is missing")


def find_mouth(frame, profile, expected_y):
    candidates = []
    for component in polish.connected_color_components(frame, profile["mouth"]):
        xs = [x for x, _ in component]
        ys = [y for _, y in component]
        center_x = sum(xs) / len(xs)
        center_y = sum(ys) / len(ys)
        if 44 <= center_x <= 52 and 20 <= center_y <= 88:
            candidates.append(
                (abs(center_x - 48) + abs(center_y - expected_y), center_x, center_y)
            )
    if not candidates:
        return None
    _, center_x, center_y = min(candidates)
    return round(center_x), round(center_y)


def verify_face(frame, row, profile, label):
    if row == rows["walk_up"]:
        return
    center_y = polish.detect_face_y(frame, row, profile)
    if row in open_eye_rows:
        verify_living_eye(frame, 40, profile, f"{label} left eye")
        if row != rows["walk_side"]:
            verify_living_eye(frame, 56, profile, f"{label} right eye")

    expected_mouth_y = 70 if row == rows["sleeping"] else int(profile["default_y"]) + 9
    mouth = find_mouth(frame, profile, expected_mouth_y)
    if mouth is None:
        raise SystemExit(f"{label}: mouth is missing")
    mouth_x, mouth_y = mouth
    mouth_region = [
        (x, y)
        for y in range(mouth_y - 2, mouth_y + 3)
        for x in range(mouth_x - 2, mouth_x + 3)
        if frame.getpixel((x, y)) in {profile["mouth"], profile["outline"]}
    ]
    mouth_width = max(x for x, _ in mouth_region) - min(x for x, _ in mouth_region) + 1
    if not 2 <= mouth_width <= 3:
        raise SystemExit(f"{label}: mouth width is {mouth_width}px, expected 2-3px")

    if row == rows["sleeping"]:
        eye_band = [
            frame.getpixel((x, y))
            for y in range(mouth_y - 18, mouth_y - 6)
            for x in range(31, 66)
        ]
        if color_count(eye_band, profile["outline"]) < 80:
            raise SystemExit(f"{label}: sleeping chevron eyelids are missing")
        if (
            color_count(eye_band, profile["white"]) > 8
            or color_count(eye_band, profile["iris"]) > 2
        ):
            raise SystemExit(f"{label}: sleeping eyes are not closed")
    elif row == rows["error"]:
        error_face = [
            frame.getpixel((x, y))
            for y in range(center_y - 16, center_y + 16)
            for x in range(31, 66)
        ]
        if color_count(error_face, profile["skin"]) < 400:
            raise SystemExit(f"{label}: character skin is not preserved")
        if color_count(error_face, profile["panic"]) >= 100:
            raise SystemExit(f"{label}: error face is incorrectly filled blue")
        if color_count(error_face, polish.THOUGHT_BLUE) < 8:
            raise SystemExit(f"{label}: tear/stress accents are missing")

    if row in (rows["idle"], rows["working"]):
        brow_band = [
            frame.getpixel((x, y))
            for y in range(center_y - 13, center_y - 7)
            for x in range(33, 64)
        ]
        if color_count(brow_band, profile["outline"]) < 15:
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
    if limited_palette and palette_size > 23:
        raise SystemExit(f"{path.name}: fleet palette expanded to {palette_size} colors")
    if not limited_palette and palette_size < 400:
        raise SystemExit(f"{path.name}: generic art appears bulk-posterized")

    profile = polish.sprite_profile(image)
    idle = image.crop((0, 0, 96, 96))
    idle_y = polish.detect_face_y(idle, rows["idle"], profile)
    hair_base, _ = polish.choose_hair_rim(idle, idle_y, profile)
    polish.configure_character_eye_colors(profile, hair_base)
    for row in range(10):
        for frame_index in range(4):
            frame = image.crop(
                (frame_index * 96, row * 96, (frame_index + 1) * 96, (row + 1) * 96)
            )
            verify_face(frame, row, profile, f"{path.name} row {row} frame {frame_index}")

    excluded = {
        polish.TRANSPARENT,
        profile["outline"],
        profile["skin"],
        profile["mouth"],
        profile["white"],
        profile["iris"],
        profile["iris_light"],
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
    (generic_dir / "_contact_sheet.png", (288, 336)),
    (fleet_dir / "_contact_sheet.png", (288, 560)),
)
for path, expected_size in contacts:
    if not path.is_file():
        raise SystemExit(f"missing contact sheet: {path}")
    actual_size = Image.open(path).size
    if actual_size != expected_size:
        raise SystemExit(f"{path}: expected {expected_size}, got {actual_size}")

print(
    "OK: verified 9 generic and 14 fleet sheets; "
    "open sclera, two-tier character irises, 1px glints, and 2-3px mouths"
)
PY
