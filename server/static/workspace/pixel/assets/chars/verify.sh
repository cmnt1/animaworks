#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
asset_dir="$(cd -- "${script_dir}/.." && pwd)"

characters=(
  sample_01 sample_02 sample_03 sample_04 sample_05 sample_06
  human customer_a customer_b
)

for character in "${characters[@]}"; do
  file="${script_dir}/${character}.png"
  [[ -f "${file}" ]] || { echo "missing sprite: ${file}" >&2; exit 1; }
  read -r format width height channels <<<"$(
    magick identify -format '%m %w %h %[channels]' "${file}"
  )"
  [[ "${format}" == "PNG" ]] || { echo "${character}: expected PNG" >&2; exit 1; }
  [[ "${width}x${height}" == "384x960" ]] || {
    echo "${character}: expected 384x960, got ${width}x${height}" >&2
    exit 1
  }
  [[ "${channels}" == *a* ]] || { echo "${character}: alpha channel missing" >&2; exit 1; }
done

python3 - "${asset_dir}/manifest.json" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
expected = {
    *(f"sample_{index:02d}" for index in range(1, 7)),
    "human",
    "customer_a",
    "customer_b",
}
chars = manifest.get("chars", {})
if set(chars) != expected:
    raise SystemExit(f"manifest chars mismatch: {sorted(chars)}")

expected_rows = {
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
for key, config in chars.items():
    if config.get("file") != f"chars/{key}.png":
        raise SystemExit(f"{key}: invalid file")
    if (config.get("frameW"), config.get("frameH")) != (96, 96):
        raise SystemExit(f"{key}: invalid frame dimensions")
    animations = config.get("anims", {})
    if set(animations) != set(expected_rows):
        raise SystemExit(f"{key}: invalid animation keys")
    for name, row in expected_rows.items():
        if animations[name].get("row") != row or animations[name].get("frames") != 4:
            raise SystemExit(f"{key}.{name}: invalid row or frame count")
PY

printf 'OK: verified generic character sheets and manifest\n'
