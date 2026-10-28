# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Prompt constants for bustup, chibi, and expression variants."""

from __future__ import annotations

from core.schemas import VALID_EMOTIONS as _VALID_EXPRESSION_NAMES

# ── Anime prompts ───────────────────────────────────────────

_BUSTUP_PROMPT = (
    "Generate a portrait of the same character from the chest up. "
    "Same outfit, same colors, same features. "
    "Anime illustration style, soft lighting, looking at viewer."
)

_CHIBI_PROMPT = (
    "Transform this character into a chibi / super-deformed version. "
    "2.5-head proportion, cute big eyes, simplified body. "
    "Same outfit colors and features. White background, full body, anime style."
)

_CHAT_ICON_PROMPT = (
    "Create a square chat avatar icon from this bust-up reference. "
    "Center the face in the frame; crop to a tight head-and-shoulders portrait. "
    "Same character identity, outfit colors, hairstyle, and features. "
    "Clean plain background, neutral soft lighting. "
    "Anime illustration style, high quality, looking at viewer."
)

# Expression-specific prompts for bustup image variants
_EXPRESSION_PROMPTS: dict[str, str] = {
    "neutral": (
        "The character with a calm relaxed expression, looking at viewer. "
        "Soft eyes, natural closed mouth, relaxed eyebrows. "
        "Arms at sides in a natural posture. "
        "Bust-up portrait, anime illustration, soft lighting. "
        "Same character identity, outfit, and hairstyle."
    ),
    "smile": (
        "Change the character's expression to a bright smile. "
        "Eyes curving upward into happy crescents, "
        "rosy flushed cheeks, joyful and cheerful expression. "
        "Head tilted slightly to one side, hands relaxed naturally. "
        "Bust-up portrait, anime illustration, soft lighting. "
        "Same character identity, outfit, and hairstyle."
    ),
    "laugh": (
        "Change the character's expression to joyful laughing. "
        "Eyes squeezed shut happily, mouth wide open showing teeth, raised cheeks. "
        "Head tilted back with amusement, one hand near mouth. "
        "Bust-up portrait, anime illustration, soft lighting. "
        "Same character identity, outfit, and hairstyle."
    ),
    "troubled": (
        "Change the character's expression to worried and troubled. "
        "Eyebrows furrowed and pinched together, slight frown, nervous eyes. "
        "Both hands clasped together in front of chest, shoulders raised tensely. "
        "Bust-up portrait, anime illustration, soft lighting. "
        "Same character identity, outfit, and hairstyle."
    ),
    "surprised": (
        "Change the character's expression to shocked surprise. "
        "Eyes wide open as large as possible, eyebrows raised very high, "
        "mouth dropped open in a round shape. "
        "Both hands raised up near face, leaning back slightly in shock. "
        "Bust-up portrait, anime illustration, soft lighting. "
        "Same character identity, outfit, and hairstyle."
    ),
    "thinking": (
        "Change the character's expression to deep contemplation. "
        "Looking slightly upward, one eye slightly narrowed, thoughtful furrowed brow. "
        "One hand on chin in a classic thinking pose, slight pout. "
        "Bust-up portrait, anime illustration, soft lighting. "
        "Same character identity, outfit, and hairstyle."
    ),
    "embarrassed": (
        "Change the character's expression to deeply embarrassed. "
        "Bright red blush across entire face, eyes averted to the side. "
        "Both hands covering cheeks or pressing index fingers together nervously. "
        "Bust-up portrait, anime illustration, soft lighting. "
        "Same character identity, outfit, and hairstyle."
    ),
}

assert set(_EXPRESSION_PROMPTS.keys()) == _VALID_EXPRESSION_NAMES, (
    f"Expression prompts mismatch: {set(_EXPRESSION_PROMPTS.keys())} != {_VALID_EXPRESSION_NAMES}"
)

# Per-expression guidance_scale for Flux Kontext.
_EXPRESSION_GUIDANCE: dict[str, float] = {
    "neutral": 3.5,
    "smile": 4.0,
    "laugh": 4.5,
    "troubled": 4.5,
    "surprised": 4.0,
    "thinking": 4.0,
    "embarrassed": 4.5,
}

assert set(_EXPRESSION_GUIDANCE.keys()) == _VALID_EXPRESSION_NAMES, (
    f"Expression guidance mismatch: {set(_EXPRESSION_GUIDANCE.keys())} != {_VALID_EXPRESSION_NAMES}"
)

# ── Realistic (photographic) prompts ──────────────────────

_REALISTIC_BUSTUP_PROMPT = (
    "Generate a portrait of the same person from the chest up. "
    "Same outfit, same colors, same features. "
    "Professional studio photograph, soft natural lighting, "
    "shallow depth of field, looking at viewer."
)

_REALISTIC_CHAT_ICON_PROMPT = (
    "Create a square chat avatar icon from this bust-up reference. "
    "Center the face in the frame; crop to a tight head-and-shoulders portrait. "
    "Same person identity, outfit, hairstyle, and features. "
    "Clean plain background, soft studio lighting. "
    "Professional photograph, natural skin texture, shallow depth of field, looking at viewer."
)

_REALISTIC_EXPRESSION_PROMPTS: dict[str, str] = {
    "neutral": (
        "The person with a calm relaxed expression, looking at viewer. "
        "Soft eyes, natural closed mouth, relaxed eyebrows. "
        "Arms at sides in a natural posture. "
        "Bust-up portrait, professional photograph, soft studio lighting. "
        "Same person identity, outfit, and hairstyle."
    ),
    "smile": (
        "Change the person's expression to a bright genuine smile. "
        "Eyes slightly narrowed with crow's feet, "
        "rosy cheeks, warm and cheerful expression. "
        "Head tilted slightly to one side, hands relaxed naturally. "
        "Bust-up portrait, professional photograph, soft studio lighting. "
        "Same person identity, outfit, and hairstyle."
    ),
    "laugh": (
        "Change the person's expression to joyful laughing. "
        "Eyes squeezed with laugh lines, mouth open showing teeth, raised cheeks. "
        "Head tilted back with amusement, one hand near mouth. "
        "Bust-up portrait, professional photograph, soft studio lighting. "
        "Same person identity, outfit, and hairstyle."
    ),
    "troubled": (
        "Change the person's expression to worried and concerned. "
        "Eyebrows furrowed and pinched together, slight frown, anxious eyes. "
        "Both hands clasped together in front of chest, shoulders raised tensely. "
        "Bust-up portrait, professional photograph, soft studio lighting. "
        "Same person identity, outfit, and hairstyle."
    ),
    "surprised": (
        "Change the person's expression to shocked surprise. "
        "Eyes wide open, eyebrows raised very high, "
        "mouth dropped open. "
        "Both hands raised up near face, leaning back slightly. "
        "Bust-up portrait, professional photograph, soft studio lighting. "
        "Same person identity, outfit, and hairstyle."
    ),
    "thinking": (
        "Change the person's expression to deep contemplation. "
        "Looking slightly upward, one eye slightly narrowed, thoughtful furrowed brow. "
        "One hand on chin in a classic thinking pose, slight pout. "
        "Bust-up portrait, professional photograph, soft studio lighting. "
        "Same person identity, outfit, and hairstyle."
    ),
    "embarrassed": (
        "Change the person's expression to visibly embarrassed. "
        "Red blush across cheeks, eyes averted to the side. "
        "Both hands covering cheeks or fidgeting nervously. "
        "Bust-up portrait, professional photograph, soft studio lighting. "
        "Same person identity, outfit, and hairstyle."
    ),
}

assert set(_REALISTIC_EXPRESSION_PROMPTS.keys()) == _VALID_EXPRESSION_NAMES, (
    f"Realistic expression prompts mismatch: {set(_REALISTIC_EXPRESSION_PROMPTS.keys())} != {_VALID_EXPRESSION_NAMES}"
)

_REALISTIC_EXPRESSION_GUIDANCE: dict[str, float] = {
    "neutral": 3.0,
    "smile": 3.5,
    "laugh": 4.0,
    "troubled": 4.0,
    "surprised": 3.5,
    "thinking": 3.5,
    "embarrassed": 4.0,
}

assert set(_REALISTIC_EXPRESSION_GUIDANCE.keys()) == _VALID_EXPRESSION_NAMES, (
    f"Realistic expression guidance mismatch: {set(_REALISTIC_EXPRESSION_GUIDANCE.keys())} != {_VALID_EXPRESSION_NAMES}"
)

# ── Pixel workspace row prompts ─────────────────────────────

# One codex image_gen call produces one animation row.  The text is intentionally
# English because it is a model prompt, not user-facing UI copy.
PIXEL_ROW_STATES: tuple[str, ...] = (
    "idle",
    "working",
    "thinking",
    "talking",
    "walk_down",
    "walk_up",
    "walk_side",
    "sleeping",
    "success",
    "error",
)

PIXEL_ROW_STATE_INSTRUCTIONS: dict[str, str] = {
    "idle": "preserve the four idle/blink expressions exactly",
    "working": "preserve the four working poses and the visible upper-body crop exactly",
    "thinking": "preserve the four thinking gestures and hand positions exactly",
    "talking": "preserve the four talking mouth/gesture phases exactly",
    "walk_down": "preserve the four front-facing walk phases exactly",
    "walk_up": "preserve the four back-facing walk phases exactly",
    "walk_side": "preserve the four side-facing walk phases exactly",
    "sleeping": "preserve the four sleeping poses and closed-eye expressions exactly",
    "success": "preserve the four success gesture phases exactly",
    "error": "preserve the four worried/error expressions and sweat marks exactly",
}

PIXEL_ROW_PROMPT_TEMPLATE = """Use case: precise-object-edit
Asset type: production pixel-art character animation strip
Primary request: Edit Image 1. Replace only the character identity with the character described below from Images 2 and 3. Keep Image 1 as the exact layout, scale, silhouette, animation, and pixel-grid target.
Input images: Image 1 is the edit target and approved base animation strip; Image 2 is the character chibi identity reference; Image 3 is the character bust-up identity and color reference.{anchor_clause}
Subject: Use the character's exact hair shape, hair color, bangs, hair accessory, eye color, and clothing colors from the identity references. Identity: {identity}. The row state is {state}: {state_instructions}.
Style/medium: crisp native pixel art, hard one-pixel edges, no antialiasing, same pixel density and outline weight as Image 1.
Composition/framing: exactly four equal left-to-right animation frames. Preserve every frame's pose, gesture, direction, crop, body size, shoulder width, head-top height, exposed face size, face center, eye/nose/mouth positions, and spacing from Image 1. Do not enlarge the face or head.
Scene/backdrop: perfectly flat solid #FF00FF chroma-key background only.
Constraints: Change only character identity colors and identity details. Preserve the clean flat skin area of the face. Eyes, eyebrows, nose, mouth, and blush must remain small, separated, readable pixel clusters matching Image 1. No new dark marks, shadows, outlines, hair strands, or isolated pixels may overlap the eyes, nose, mouth, cheeks, or exposed face. Keep dark hair clearly separated from the face boundary. The background must be one uniform #FF00FF with no shadows, gradients, texture, floor, or lighting variation.
Avoid: extra frames, merged frames, panels, borders, labels, text, speech bubbles, props, desk, chair, monitor, keyboard, cast shadow, reflection, watermark, smooth vector edges, painterly shading, facial moles, facial dirt, black blobs, stray dark pixels, and any dark patch crossing onto the face."""


PIXEL_ROW_ANCHOR_CLAUSE = (
    " Image {index} is the already finished idle row of this same character: match its hair color, hair length,"
    " bangs, eye color, skin tone, and clothing colors exactly, overriding any other reading of Images 2 and 3."
)


def build_pixel_row_prompt(
    *,
    state: str,
    state_instructions: str,
    identity: str,
    image_count: int = 3,
    has_anchor: bool = False,
) -> str:
    """Return the row prompt with the state and identity description filled in.

    *image_count* is the number of images before the optional anchor, which is
    passed last.
    """
    anchor_clause = PIXEL_ROW_ANCHOR_CLAUSE.format(index=image_count + 1) if has_anchor else ""
    return PIXEL_ROW_PROMPT_TEMPLATE.format(
        identity=identity,
        state=state,
        state_instructions=state_instructions,
        anchor_clause=anchor_clause,
    )
