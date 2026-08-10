#!/usr/bin/env bash
set -euo pipefail

scene_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
assets_dir="$(cd -- "${scene_dir}/.." && pwd)"

python3 - "${assets_dir}/manifest.json" "${scene_dir}" <<'PY'
import json
import sys
from pathlib import Path

from PIL import Image

manifest_path = Path(sys.argv[1])
scene_dir = Path(sys.argv[2])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
scene = manifest["scene"]

expected_items = {f"item_{index:02d}" for index in range(1, 15)}
if set(scene["items"]) != expected_items:
    raise SystemExit("scene item keys must be item_01 through item_14")
if "desk_taka" not in scene["props"]:
    raise SystemExit("scene props must declare desk_taka")
if "wall_bottom" not in scene["walls"]:
    raise SystemExit("scene walls must declare wall_bottom")
if "door_frame" not in scene["props"]:
    raise SystemExit("scene props must declare door_frame")

expected_prop_sizes = {
    "desk": (112, 72),
    "desk_taka": (136, 80),
    "door_frame": (192, 112),
    "desk64": (108, 48),
    "chair64": (39, 58),
    "pc_laptop": (26, 18),
    "pc_desktop": (32, 24),
    "prop_mug": (16, 16),
    "prop_plant": (20, 24),
}
for prop_name, expected_size in expected_prop_sizes.items():
    prop = scene["props"][prop_name]
    if (prop["w"], prop["h"]) != expected_size:
        raise SystemExit(
            f"{prop_name}: manifest size must be {expected_size}, "
            f"got {(prop['w'], prop['h'])}"
        )

entries = [
    *scene["tiles"].values(),
    *scene["walls"].values(),
    *scene["props"].values(),
    *scene["items"].values(),
]
if len(entries) != 55:
    raise SystemExit(f"expected 55 scene assets, got {len(entries)}")
for entry in entries:
    for field in ("file", "w", "h", "anchor"):
        if field not in entry:
            raise SystemExit(f"manifest entry missing {field}: {entry}")
    path = manifest_path.parent / entry["file"]
    if not path.is_file():
        raise SystemExit(f"missing scene asset: {entry['file']}")
    with Image.open(path) as image:
        if image.format != "PNG":
            raise SystemExit(f"not a PNG: {entry['file']}")
        if image.size != (entry["w"], entry["h"]):
            raise SystemExit(
                f"{entry['file']}: expected {(entry['w'], entry['h'])}, got {image.size}"
            )

for prop_name in (
    "door_frame",
    "desk",
    "desk_taka",
    "desk64",
    "chair64",
    "pc_laptop",
    "pc_desktop",
    "prop_mug",
    "prop_plant",
):
    prop_path = manifest_path.parent / scene["props"][prop_name]["file"]
    with Image.open(prop_path) as image:
        alpha_values = set(
            image.convert("RGBA").getchannel("A").get_flattened_data()
        )
        if not alpha_values <= {0, 255} or 0 not in alpha_values:
            raise SystemExit(
                f"{prop_path.name} must use clean binary transparency"
            )

for tile_name in ("wood_warm", "wood_cool"):
    tile_path = manifest_path.parent / scene["tiles"][tile_name]["file"]
    with Image.open(tile_path) as image:
        rgb = image.convert("RGB")
        top = [rgb.getpixel((x, 0)) for x in range(32)]
        left = [rgb.getpixel((0, y)) for y in range(32)]
        if len(set(top + left)) != 1:
            raise SystemExit(f"{tile_path.name}: grout must be a solid 1px top/left edge")
        grout = top[0]
        if all(rgb.getpixel((x, 1)) == grout for x in range(1, 32)):
            raise SystemExit(f"{tile_path.name}: top grout is thicker than 1px")
        if all(rgb.getpixel((1, y)) == grout for y in range(1, 32)):
            raise SystemExit(f"{tile_path.name}: left grout is thicker than 1px")
        interior = [
            rgb.getpixel((x, y))
            for y in range(1, 32)
            for x in range(1, 32)
        ]
        grout_luma = sum(grout) / 3
        interior_luma = sum(sum(pixel) / 3 for pixel in interior) / len(interior)
        if grout_luma >= interior_luma:
            raise SystemExit(f"{tile_path.name}: grout must be darker than the floor")

disk_items = {path.stem for path in scene_dir.glob("item_*.png")}
if disk_items != expected_items:
    raise SystemExit(f"unexpected item assets: {sorted(disk_items ^ expected_items)}")
PY

printf 'OK: verified generic scene assets and manifest\n'
