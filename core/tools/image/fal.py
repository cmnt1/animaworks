# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Fal.ai Flux Kontext and Flux Pro text-to-image API clients."""

from __future__ import annotations

import time
from typing import Any

import httpx

from core.tools._base import get_credential

from .constants import (
    _DOWNLOAD_TIMEOUT,
    _HTTP_TIMEOUT,
    FAL_FLUX_PRO_SUBMIT_URL,
    FAL_KONTEXT_SUBMIT_URL,
)
from .utils import _image_to_data_uri, _retry


class FluxKontextClient:
    """Flux Kontext [pro] client via fal.ai for reference-based generation."""

    POLL_INTERVAL = 2.0  # seconds
    POLL_TIMEOUT = 120.0  # seconds

    def __init__(self) -> None:
        self._key = get_credential("fal", "image_gen", env_var="FAL_KEY")

    def generate_from_reference(
        self,
        reference_image: bytes,
        prompt: str,
        aspect_ratio: str = "3:4",
        output_format: str = "png",
        guidance_scale: float = 3.5,
        seed: int | None = None,
    ) -> bytes:
        """Generate an image from a reference image with Flux Kontext.

        Returns:
            PNG (or JPEG) image bytes.
        """
        data_uri = _image_to_data_uri(reference_image)
        payload: dict[str, Any] = {
            "prompt": prompt,
            "image_url": data_uri,
            "aspect_ratio": aspect_ratio,
            "output_format": output_format,
            "guidance_scale": guidance_scale,
            "num_images": 1,
            "safety_tolerance": "6",
        }
        if seed is not None:
            payload["seed"] = seed

        headers = {
            "Authorization": f"Key {self._key}",
            "Content-Type": "application/json",
        }

        def _submit() -> dict[str, str]:
            resp = httpx.post(
                FAL_KONTEXT_SUBMIT_URL,
                json=payload,
                headers=headers,
                timeout=_HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "request_id": data["request_id"],
                "status_url": data["status_url"],
                "response_url": data["response_url"],
            }

        submit_data = _retry(_submit)
        request_id = submit_data["request_id"]

        result_url = submit_data["response_url"]
        status_url = submit_data["status_url"]
        deadline = time.monotonic() + self.POLL_TIMEOUT

        while time.monotonic() < deadline:
            time.sleep(self.POLL_INTERVAL)
            status_resp = httpx.get(
                status_url,
                headers=headers,
                timeout=_HTTP_TIMEOUT,
            )
            status_resp.raise_for_status()
            status_data = status_resp.json()
            if status_data.get("status") == "COMPLETED":
                break
            if status_data.get("status") == "FAILED":
                raise RuntimeError(f"Flux Kontext task {request_id} failed: {status_data.get('error', 'unknown')}")
        else:
            raise TimeoutError(f"Flux Kontext task {request_id} timed out after {self.POLL_TIMEOUT}s")

        result_resp = httpx.get(
            result_url,
            headers=headers,
            timeout=_HTTP_TIMEOUT,
        )
        result_resp.raise_for_status()
        result_data = result_resp.json()

        images = result_data.get("images", [])
        if not images:
            raise ValueError("Flux Kontext returned no images")

        image_url = images[0]["url"]
        img_resp = httpx.get(image_url, timeout=_DOWNLOAD_TIMEOUT)
        img_resp.raise_for_status()
        return img_resp.content


class FalTextToImageClient:
    """Fal.ai Flux Pro text-to-image client (fallback for NovelAI)."""

    POLL_INTERVAL = 2.0  # seconds
    POLL_TIMEOUT = 120.0  # seconds

    def __init__(self) -> None:
        self._key = get_credential("fal", "image_gen", env_var="FAL_KEY")

    def generate_fullbody(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 768,
        height: int = 1024,
        seed: int | None = None,
        output_format: str = "png",
        guidance_scale: float = 3.5,
        steps: int = 28,
        scale: float = 5.0,
        sampler: str = "k_euler_ancestral",
        vibe_image: bytes | None = None,
        vibe_strength: float = 0.6,
        vibe_info_extracted: float = 0.8,
        face_reference_image: bytes | None = None,
    ) -> bytes:
        """Generate a full-body character image from text prompt.

        When *face_reference_image* is provided, delegates to
        :class:`FluxKontextClient` which uses the face photo as a reference
        base and applies the character prompt on top, preserving facial
        identity in the generated image.

        Uses fal.ai Flux Pro v1.1 otherwise.  Compatible with the same
        call signature as :meth:`NovelAIClient.generate_fullbody` but
        ignores NovelAI-specific parameters (vibe transfer, sampler, etc.).

        Returns:
            PNG image bytes.
        """
        if face_reference_image is not None:
            kontext = FluxKontextClient()
            return kontext.generate_from_reference(
                reference_image=face_reference_image,
                prompt=prompt,
                aspect_ratio="3:4",
                output_format=output_format,
                seed=seed,
            )

        payload: dict[str, Any] = {
            "prompt": prompt,
            "image_size": {"width": width, "height": height},
            "output_format": output_format,
            "guidance_scale": guidance_scale,
            "num_images": 1,
            "safety_tolerance": "6",
        }
        if seed is not None:
            payload["seed"] = seed

        headers = {
            "Authorization": f"Key {self._key}",
            "Content-Type": "application/json",
        }

        def _submit() -> dict[str, str]:
            resp = httpx.post(
                FAL_FLUX_PRO_SUBMIT_URL,
                json=payload,
                headers=headers,
                timeout=_HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "request_id": data["request_id"],
                "status_url": data["status_url"],
                "response_url": data["response_url"],
            }

        submit_data = _retry(_submit)
        request_id = submit_data["request_id"]

        result_url = submit_data["response_url"]
        status_url = submit_data["status_url"]
        deadline = time.monotonic() + self.POLL_TIMEOUT

        while time.monotonic() < deadline:
            time.sleep(self.POLL_INTERVAL)
            status_resp = httpx.get(
                status_url,
                headers=headers,
                timeout=_HTTP_TIMEOUT,
            )
            status_resp.raise_for_status()
            status_data = status_resp.json()
            if status_data.get("status") == "COMPLETED":
                break
            if status_data.get("status") == "FAILED":
                raise RuntimeError(f"Fal Flux Pro task {request_id} failed: {status_data.get('error', 'unknown')}")
        else:
            raise TimeoutError(f"Fal Flux Pro task {request_id} timed out after {self.POLL_TIMEOUT}s")

        result_resp = httpx.get(
            result_url,
            headers=headers,
            timeout=_HTTP_TIMEOUT,
        )
        result_resp.raise_for_status()
        result_data = result_resp.json()

        images = result_data.get("images", [])
        if not images:
            raise ValueError("Fal Flux Pro returned no images")

        image_url = images[0]["url"]
        img_resp = httpx.get(image_url, timeout=_DOWNLOAD_TIMEOUT)
        img_resp.raise_for_status()
        return img_resp.content
