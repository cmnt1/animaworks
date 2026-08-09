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

# Status bubbles with text are drawn programmatically (PixelMplus10).
# Only icon / accent FX sprites remain as files.
check_png bubble_small.png 64x128
check_png envelope.png 128x32
check_png parcel.png 64x32
check_png heart.png 64x16
check_png sparkle.png 64x16
check_png smoke.png 128x32
check_png flash.png 128x32
check_png moon.png 32x32
check_png sun.png 32x32
check_png clock.png 64x16
test -s "$fx_dir/_contact_sheet.png"

for file in \
    bubble_small.png envelope.png parcel.png heart.png \
    sparkle.png smoke.png flash.png moon.png sun.png clock.png; do
    check_alpha "$file"
done

python3 - "$manifest" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
data = json.loads(manifest_path.read_text(encoding="utf-8"))

expected = {
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
    "clock": ("fx/clock.png", 0, 4, 4),
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

echo "verified FX sprite files and contact sheet"
