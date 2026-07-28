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
if "desk_human" not in scene["props"]:
    raise SystemExit("scene props must declare desk_human")

entries = [
    *scene["tiles"].values(),
    *scene["walls"].values(),
    *scene["props"].values(),
    *scene["items"].values(),
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

disk_items = {path.stem for path in scene_dir.glob("item_*.png")}
if disk_items != expected_items:
    raise SystemExit(f"unexpected item assets: {sorted(disk_items ^ expected_items)}")
PY

printf 'OK: verified generic scene assets and manifest\n'
