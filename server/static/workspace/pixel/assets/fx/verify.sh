#!/usr/bin/env bash
set -euo pipefail

fx_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
assets_dir="$(cd "$fx_dir/.." && pwd)"
manifest="$assets_dir/manifest.json"

command -v magick >/dev/null
command -v python3 >/dev/null

check_png() {
    local file="$1"
    local expected="$2"
    local actual

    test -s "$fx_dir/$file"
    actual="$(magick identify -format '%m %wx%h' "$fx_dir/$file")"
    if [[ "$actual" != "PNG $expected" ]]; then
        echo "$file: expected PNG $expected, got $actual" >&2
        return 1
    fi
}

check_alpha() {
    local file="$1"
    local channels

    channels="$(magick identify -format '%[channels]' "$fx_dir/$file")"
    if [[ "$channels" != *a* ]]; then
        echo "$file: expected an alpha channel, got $channels" >&2
        return 1
    fi
}

check_png bubbles.png 192x288
check_png bubble_small.png 64x128
check_png envelope.png 128x32
check_png parcel.png 64x32
check_png heart.png 64x16
check_png sparkle.png 64x16
check_png smoke.png 128x32
check_png flash.png 128x32
check_png moon.png 32x32
check_png sun.png 32x32
test -s "$fx_dir/_contact_sheet.png"

for file in \
    bubbles.png bubble_small.png envelope.png parcel.png heart.png \
    sparkle.png smoke.png flash.png moon.png sun.png; do
    check_alpha "$file"
done

python3 - "$manifest" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
data = json.loads(manifest_path.read_text(encoding="utf-8"))

expected = {
    "bubble_working": ("fx/bubbles.png", 0, 2, 2),
    "bubble_thinking": ("fx/bubbles.png", 1, 2, 2),
    "bubble_meeting": ("fx/bubbles.png", 2, 2, 2),
    "bubble_sleeping": ("fx/bubbles.png", 3, 2, 2),
    "bubble_reporting": ("fx/bubbles.png", 4, 2, 2),
    "bubble_error": ("fx/bubbles.png", 5, 2, 2),
    "bubble_break": ("fx/bubbles.png", 6, 2, 2),
    "bubble_instruction": ("fx/bubbles.png", 7, 2, 2),
    "bubble_delivery": ("fx/bubbles.png", 8, 2, 2),
    "bubble_small_question": ("fx/bubble_small.png", 0, 2, 2),
    "bubble_small_exclamation": ("fx/bubble_small.png", 1, 2, 2),
    "bubble_small_music": ("fx/bubble_small.png", 2, 2, 2),
    "bubble_small_sleep": ("fx/bubble_small.png", 3, 2, 2),
    "envelope": ("fx/envelope.png", 0, 4, 8),
    "parcel": ("fx/parcel.png", 0, 2, 3),
    "heart": ("fx/heart.png", 0, 4, 8),
    "sparkle": ("fx/sparkle.png", 0, 4, 8),
    "smoke": ("fx/smoke.png", 0, 4, 6),
    "flash": ("fx/flash.png", 0, 4, 8),
    "moon": ("fx/moon.png", 0, 1, 1),
    "sun": ("fx/sun.png", 0, 1, 1),
}

fx = data.get("fx")
if not isinstance(fx, dict):
    raise SystemExit("manifest.json: fx must be an object")
if set(fx) != set(expected):
    missing = sorted(set(expected) - set(fx))
    extra = sorted(set(fx) - set(expected))
    raise SystemExit(f"manifest.json: fx key mismatch; missing={missing}, extra={extra}")

for key, (file, row, frames, fps) in expected.items():
    actual = fx[key]
    wanted = {"file": file, "row": row, "frames": frames, "fps": fps}
    if actual != wanted:
        raise SystemExit(f"manifest.json: {key}: expected {wanted}, got {actual}")

print(f"verified {len(expected)} manifest fx entries")
PY

echo "verified 10 FX sprite files and contact sheet"
