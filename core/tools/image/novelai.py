# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""NovelAI V4.5 API client for anime full-body image generation."""

from __future__ import annotations

import base64
import io
import zipfile
from typing import Any

import httpx

from core.tools._base import get_credential, logger

from .constants import (
    _HTTP_TIMEOUT,
    NOVELAI_API_URL,
    NOVELAI_ENCODE_URL,
    NOVELAI_MODEL,
)
from .utils import _retry


class NovelAIClient:
    """NovelAI V4.5 API client for anime full-body image generation."""

    def __init__(self) -> None:
        self._token = get_credential("novelai", "image_gen", env_var="NOVELAI_TOKEN")

    def encode_vibe(
        self,
        image: bytes,
        information_extracted: float = 0.8,
    ) -> bytes:
        """Encode an image into V4+ vibe binary via /ai/encode-vibe.

        The NovelAI V4/V4.5 API requires images to be pre-encoded into
        vibe representations before they can be used as style references.
        This costs 2 Anlas per encoding.

        Returns:
            Binary vibe data (~48 KB).
        """
        b64 = base64.b64encode(image).decode()
        body = {
            "image": b64,
            "model": NOVELAI_MODEL,
            "information_extracted": information_extracted,
        }

        def _call() -> bytes:
            resp = httpx.post(
                NOVELAI_ENCODE_URL,
                json=body,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                timeout=_HTTP_TIMEOUT,
            )
            if resp.status_code != 200:
                logger.error(
                    "NovelAI encode-vibe error %d: %s",
                    resp.status_code,
                    resp.text[:500],
                )
            resp.raise_for_status()
            return resp.content

        return _retry(_call)

    def generate_fullbody(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1536,
        seed: int | None = None,
        steps: int = 28,
        scale: float = 5.0,
        sampler: str = "k_euler_ancestral",
        vibe_image: bytes | None = None,
        vibe_strength: float = 0.6,
        vibe_info_extracted: float = 0.8,
        face_reference_image: bytes | None = None,
    ) -> bytes:
        """Generate a full-body anime character image.

        When *face_reference_image* is provided and no *vibe_image* is given,
        the face photo is used as the Vibe Transfer reference so the generated
        character's style and features reflect the supplied face.

        Returns:
            PNG image bytes.
        """
        neg = negative_prompt or (
            "lowres, bad anatomy, bad hands, missing fingers, extra digits, "
            "fewer digits, worst quality, low quality, blurry, jpeg artifacts, "
            "cropped, multiple views, logo, too many watermarks"
        )

        params: dict[str, Any] = {
            "width": width,
            "height": height,
            "scale": scale,
            "sampler": sampler,
            "steps": steps,
            "n_samples": 1,
            "ucPreset": 0,
            "qualityToggle": True,
            "sm": False,
            "sm_dyn": False,
            "dynamic_thresholding": False,
            "legacy": False,
            "cfg_rescale": 0,
            "noise_schedule": "native",
            "negative_prompt": neg,
            "v4_prompt": {
                "caption": {
                    "base_caption": prompt,
                    "char_captions": [],
                },
                "use_coords": False,
                "use_order": True,
            },
            "v4_negative_prompt": {
                "caption": {
                    "base_caption": neg,
                    "char_captions": [],
                },
                "legacy_uc": False,
            },
            "reference_image_multiple": [],
            "reference_information_extracted_multiple": [],
            "reference_strength_multiple": [],
        }
        if seed is not None:
            params["seed"] = seed

        # Vibe Transfer – V4+ requires pre-encoded vibe data.
        # face_reference_image is used as vibe source when no explicit style
        # reference (vibe_image) was provided via Style From.
        effective_vibe = vibe_image if vibe_image is not None else face_reference_image
        if effective_vibe is not None:
            encoded = self.encode_vibe(effective_vibe, vibe_info_extracted)
            b64 = base64.b64encode(encoded).decode()
            params["reference_image_multiple"] = [b64]
            params["reference_information_extracted_multiple"] = [vibe_info_extracted]
            params["reference_strength_multiple"] = [vibe_strength]

        body = {
            "input": prompt,
            "model": NOVELAI_MODEL,
            "action": "generate",
            "parameters": params,
        }

        def _call() -> bytes:
            resp = httpx.post(
                NOVELAI_API_URL,
                json=body,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                timeout=_HTTP_TIMEOUT,
            )
            if resp.status_code != 200:
                logger.error(
                    "NovelAI generate error %d: %s",
                    resp.status_code,
                    resp.text[:500],
                )
            resp.raise_for_status()
            return self._extract_png(resp.content)

        return _retry(_call)

    @staticmethod
    def _extract_png(data: bytes) -> bytes:
        """Extract the first PNG from a ZIP-compressed response."""
        buf = io.BytesIO(data)
        with zipfile.ZipFile(buf) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".png"):
                    return zf.read(name)
        raise ValueError("NovelAI response ZIP contains no PNG file")
