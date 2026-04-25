# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""NanoGPT API client for image generation (text-to-image / image-to-image)."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable

import httpx

from core.paths import get_data_dir
from core.tools._base import get_credential, logger

from .constants import _HTTP_TIMEOUT
from .utils import _retry

NANOGPT_API_URL = "https://nano-gpt.com/v1/images/generations"

# Models available on NanoGPT subscription plans.
NANOGPT_SUBSCRIPTION_MODELS = ("chroma", "hidream", "qwen-image", "z-image-turbo")


# Models that support image-to-image via imageDataUrl parameter.
NANOGPT_IMG2IMG_MODELS = frozenset({"hidream"})
NANOGPT_IMAGE_MODEL_CATALOG_CACHE_FILE = "image_model_catalog_cache.json"


def _cached_img2img_models() -> set[str]:
    path = get_data_dir() / NANOGPT_IMAGE_MODEL_CATALOG_CACHE_FILE
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    providers = data.get("providers") if isinstance(data, dict) else None
    entry = providers.get("nanogpt") if isinstance(providers, dict) else None
    models = entry.get("models") if isinstance(entry, dict) else None
    if not isinstance(models, list):
        return set()
    return {
        str(model.get("id", "")).strip()
        for model in models
        if isinstance(model, dict) and model.get("image_to_image") is True and str(model.get("id", "")).strip()
    }


def supports_image_to_image(model: str) -> bool:
    return model in NANOGPT_IMG2IMG_MODELS or model in _cached_img2img_models()


class NanoGPTImageClient:
    """NanoGPT API client for image generation.

    Uses the OpenAI-compatible image generation endpoint.
    Subscription models: chroma, hidream, qwen-image, z-image-turbo.
    hidream supports image-to-image via ``imageDataUrl``.
    """

    def __init__(self, model: str = "chroma") -> None:
        self._token = get_credential("nanogpt", "image_gen", env_var="NANOGPT_API_KEY")
        self._model = model

    def generate_fullbody(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 512,
        height: int = 512,
        seed: int | None = None,
        steps: int = 28,
        scale: float = 5.0,
        sampler: str = "k_euler_ancestral",
        vibe_image: bytes | None = None,
        vibe_strength: float = 0.6,
        vibe_info_extracted: float = 0.8,
        face_reference_image: bytes | None = None,
        step_callback: Callable[[int, int], None] | None = None,
    ) -> bytes:
        """Generate a full-body character image via NanoGPT API.

        Compatible with the same call signature as
        :meth:`NovelAIClient.generate_fullbody`.  Ignores vibe transfer,
        sampler, and step callback.  For image-to-image capable models
        (e.g. hidream), ``face_reference_image`` is sent as
        ``imageDataUrl``.

        Returns:
            PNG image bytes.
        """
        payload: dict[str, object] = {
            "model": self._model,
            "prompt": prompt,
            "n": 1,
            "size": f"{width}x{height}",
            "response_format": "b64_json",
        }
        if seed is not None:
            payload["seed"] = seed

        # Image-to-image: send face reference as imageDataUrl for supported models
        if face_reference_image is not None and supports_image_to_image(self._model):
            b64_ref = base64.b64encode(face_reference_image).decode()
            payload["imageDataUrl"] = f"data:image/png;base64,{b64_ref}"
            logger.info("NanoGPT img2img: sending face reference (%d bytes)", len(face_reference_image))

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        def _call() -> bytes:
            resp = httpx.post(
                NANOGPT_API_URL,
                json=payload,
                headers=headers,
                timeout=_HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            # Log cost for monitoring
            cost = data.get("cost")
            if cost is not None:
                logger.info(
                    "NanoGPT image generated (model=%s, cost=%s)",
                    self._model,
                    cost,
                )

            images = data.get("data", [])
            if not images:
                raise RuntimeError(f"NanoGPT returned no images (model={self._model})")

            b64 = images[0].get("b64_json")
            if not b64:
                # Fall back to URL-based response
                url = images[0].get("url")
                if url:
                    img_resp = httpx.get(url, timeout=_HTTP_TIMEOUT)
                    img_resp.raise_for_status()
                    return img_resp.content
                raise RuntimeError("NanoGPT response missing both b64_json and url")

            return base64.b64decode(b64)

        return _retry(_call)
