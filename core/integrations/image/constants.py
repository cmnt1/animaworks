# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""URL constants, timeouts, and execution profiles for image/3D generation."""

from __future__ import annotations

import httpx

# ── Execution Profile ─────────────────────────────────────

EXECUTION_PROFILE: dict[str, dict[str, object]] = {
    "pipeline": {"expected_seconds": 1800, "background_eligible": True},
    "3d": {"expected_seconds": 600, "background_eligible": True},
    "rigging": {"expected_seconds": 600, "background_eligible": True},
    "animations": {"expected_seconds": 600, "background_eligible": True},
    "fullbody": {"expected_seconds": 120, "background_eligible": True},
    "bustup": {"expected_seconds": 120, "background_eligible": True},
    "icon": {"expected_seconds": 120, "background_eligible": True},
    "chibi": {"expected_seconds": 120, "background_eligible": True},
}

# ── URL Constants ──────────────────────────────────────────

NOVELAI_API_URL = "https://image.novelai.net/ai/generate-image"
NOVELAI_ENCODE_URL = "https://image.novelai.net/ai/encode-vibe"
NOVELAI_MODEL = "nai-diffusion-4-5-full"

FAL_KONTEXT_SUBMIT_URL = "https://queue.fal.run/fal-ai/flux-pro/kontext"
FAL_FLUX_PRO_SUBMIT_URL = "https://queue.fal.run/fal-ai/flux-pro/v1.1"

MESHY_IMAGE_TO_3D_URL = "https://api.meshy.ai/openapi/v1/image-to-3d"
MESHY_TASK_URL_TPL = "https://api.meshy.ai/openapi/v1/image-to-3d/{task_id}"
MESHY_RIGGING_URL = "https://api.meshy.ai/openapi/v1/rigging"
MESHY_RIGGING_TASK_TPL = "https://api.meshy.ai/openapi/v1/rigging/{task_id}"
MESHY_ANIMATION_URL = "https://api.meshy.ai/openapi/v1/animations"
MESHY_ANIMATION_TASK_TPL = "https://api.meshy.ai/openapi/v1/animations/{task_id}"

# ── Timeouts & Retry ───────────────────────────────────────

_HTTP_TIMEOUT = httpx.Timeout(30.0, read=120.0)
_DOWNLOAD_TIMEOUT = httpx.Timeout(60.0, read=300.0)

_RETRYABLE_CODES = {429, 500, 502, 503}

# Default animation presets for office digital animas
# See https://docs.meshy.ai/api/animation-library for full catalog
_DEFAULT_ANIMATIONS: dict[str, int] = {
    "idle": 0,
    "sitting": 32,
    "waving": 28,
    "talking": 307,
}
