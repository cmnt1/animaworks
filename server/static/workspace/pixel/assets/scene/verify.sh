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

office_bg = scene_dir / "office_bg.png"
if office_bg.is_file():
    with Image.open(office_bg) as image:
        if image.size != (1120, 736):
            raise SystemExit(f"office_bg.png: expected 1120x736, got {image.size}")

if "items" in scene:
    raise SystemExit("legacy scene items must not be declared")
if "desk_taka" not in scene["props"]:
    raise SystemExit("scene props must declare desk_taka")
if set(scene["walls"]) != {"segment", "plain"}:
    raise SystemExit("scene walls must declare segment and plain")
if set(scene["tiles"]) != {"floor_wood", "floor_carpet"}:
    raise SystemExit("scene tiles must declare floor_wood and floor_carpet")

expected_prop_sizes = {
    "desk": (112, 72),
    "desk_taka": (136, 80),
    "whiteboard": (160, 72),
    "coffee_corner": (96, 72),
    "sofa": (96, 56),
    "vending": (56, 88),
    "server_rack": (56, 88),
    "meeting_table": (96, 56),
    "welcome_mat": (96, 48),
    "entrance": (176, 120),
    "bookshelf": (112, 64),
    "plant_large": (32, 56),
    "cat": (28, 20),
    "rug": (144, 96),
    "trash_bin": (20, 28),
    "side_table": (56, 44),
    "trolley": (56, 56),
    "cat_bed": (32, 20),
    "sign_stand": (24, 44),
    "poster_a": (24, 36),
    "poster_b": (24, 36),
    "desk64": (108, 48),
    "chair64": (39, 58),
    "pc_laptop": (26, 18),
    "pc_desktop": (32, 24),
    "prop_mug": (16, 16),
    "prop_plant": (20, 24),
    "prop_documents": (20, 16),
    "prop_papers_stack": (20, 12),
    "prop_pen_stand": (12, 20),
    "prop_books": (22, 16),
    "prop_book_open": (24, 16),
    "prop_binder": (20, 20),
    "prop_sticky_notes": (14, 10),
    "prop_photo_frame": (16, 20),
    "prop_tissue_box": (20, 14),
    "prop_headphones": (22, 16),
    "prop_water_bottle": (10, 22),
    "prop_figurine": (12, 20),
    "prop_mug_red": (16, 16),
    "prop_mug_green": (16, 16),
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
]
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
    "entrance",
    "whiteboard",
    "coffee_corner",
    "sofa",
    "vending",
    "server_rack",
    "meeting_table",
    "welcome_mat",
    "bookshelf",
    "plant_large",
    "cat",
    "rug",
    "trash_bin",
    "side_table",
    "trolley",
    "cat_bed",
    "sign_stand",
    "poster_a",
    "poster_b",
    "desk",
    "desk_taka",
    "desk64",
    "chair64",
    "pc_laptop",
    "pc_desktop",
    "prop_mug",
    "prop_plant",
    "prop_documents",
    "prop_papers_stack",
    "prop_pen_stand",
    "prop_books",
    "prop_book_open",
    "prop_binder",
    "prop_sticky_notes",
    "prop_photo_frame",
    "prop_tissue_box",
    "prop_headphones",
    "prop_water_bottle",
    "prop_figurine",
    "prop_mug_red",
    "prop_mug_green",
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

for tile_name in ("floor_wood", "floor_carpet"):
    tile_path = manifest_path.parent / scene["tiles"][tile_name]["file"]
    with Image.open(tile_path) as image:
        rgb = image.convert("RGB")
        if any(rgb.getpixel((0, y)) != rgb.getpixel((127, y)) for y in range(128)):
            raise SystemExit(f"{tile_path.name}: horizontal seam mismatch")
        if any(rgb.getpixel((x, 0)) != rgb.getpixel((x, 127)) for x in range(128)):
            raise SystemExit(f"{tile_path.name}: vertical seam mismatch")

if list(scene_dir.glob("item_*.png")):
    raise SystemExit("legacy item assets must be removed")
PY

printf 'OK: verified generic scene assets and manifest\n'
