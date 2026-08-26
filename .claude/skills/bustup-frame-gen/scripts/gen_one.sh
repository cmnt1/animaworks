#!/bin/bash
# $1 = expression dir
cd "$1" || exit 1
timeout 600 grok --always-approve -p "You are doing image editing only. The file ./src.png is an anime character bustup. Using the image_edit tool with src.png as the source, create exactly 3 edited variants in the current directory. CRITICAL: each variant must be IDENTICAL to the source in every way (pose, hair, clothes, colors, lighting, composition, framing, art style, and the source's facial expression) except the single described change:
1. eyes_closed.png — both eyes gently closed (relaxed blink, lashes down). Mouth unchanged from source.
2. mouth_half.png — mouth slightly open as if speaking softly. Eyes unchanged from source.
3. mouth_open.png — mouth clearly open as if speaking a vowel (natural, not shouting). Eyes unchanged from source.
Save each output as PNG with those exact filenames. After creating all 3, run 'ls -la *.png' and stop."
