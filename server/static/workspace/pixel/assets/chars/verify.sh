#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
asset_dir="$(cd -- "${script_dir}/.." && pwd)"

python3 - "${asset_dir}/manifest.json" "${script_dir}/sample_01.png" <<'PY'
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops

manifest_path = Path(sys.argv[1])
sheet_path = Path(sys.argv[2])
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

chars = json.loads(manifest_path.read_text(encoding="utf-8")).get("chars", {})
if set(chars) != {"sample_01", "human", "customer_a", "customer_b"}:
    raise SystemExit(f"manifest chars mismatch: {sorted(chars)}")
config = chars["sample_01"]
if config.get("file") != "chars/sample_01.png":
    raise SystemExit("sample_01: invalid file")
if (config.get("frameW"), config.get("frameH")) != (64, 64):
    raise SystemExit("sample_01: invalid frame dimensions")
animations = config.get("anims", {})
if set(animations) != set(rows):
    raise SystemExit("sample_01: invalid animation keys")
for state, row in rows.items():
    if animations[state].get("row") != row or animations[state].get("frames") != 4:
        raise SystemExit(f"sample_01.{state}: invalid row or frame count")

with Image.open(sheet_path) as source:
    sheet = source.convert("RGBA")
if sheet.size != (256, 640):
    raise SystemExit(f"sample_01.png: expected 256x640, got {sheet.size}")
if not set(sheet.getchannel("A").get_flattened_data()) <= {0, 255}:
    raise SystemExit("sample_01.png: soft alpha / antialiasing found")

for row in range(10):
    if not sheet.crop((0, row * 64, 256, (row + 1) * 64)).getbbox():
        raise SystemExit(f"sample_01.png: row {row} is empty")

print("OK: verified 64px sample_01 sheet and manifest")
PY
