# AnimaWorks - Digital Person Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.

"""Character image & 3-D model generation tool for AnimaWorks.

Pipeline:
  1. NovelAI V4.5 → anime full-body image
  2. Flux Kontext [pro] (fal.ai) → bust-up from reference
  3. Flux Kontext [pro] (fal.ai) → chibi from reference
  4. Meshy Image-to-3D → GLB model from chibi image
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import sys
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from core.tools._base import ToolConfigError, get_env_or_fail, logger

# ── Constants ──────────────────────────────────────────────

NOVELAI_API_URL = "https://image.novelai.net/ai/generate-image"
NOVELAI_MODEL = "nai-diffusion-4-5-full"

FAL_KONTEXT_SUBMIT_URL = "https://queue.fal.run/fal-ai/flux-pro/kontext"
FAL_KONTEXT_STATUS_TPL = (
    "https://queue.fal.run/fal-ai/flux-pro/kontext/requests/{request_id}/status"
)
FAL_KONTEXT_RESULT_TPL = (
    "https://queue.fal.run/fal-ai/flux-pro/kontext/requests/{request_id}"
)

MESHY_IMAGE_TO_3D_URL = "https://api.meshy.ai/openapi/v1/image-to-3d"
MESHY_TASK_URL_TPL = "https://api.meshy.ai/openapi/v1/image-to-3d/{task_id}"
MESHY_RIGGING_URL = "https://api.meshy.ai/openapi/v1/rigging"
MESHY_RIGGING_TASK_TPL = "https://api.meshy.ai/openapi/v1/rigging/{task_id}"

# Default prompts for Kontext derivation
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

_HTTP_TIMEOUT = httpx.Timeout(30.0, read=120.0)
_DOWNLOAD_TIMEOUT = httpx.Timeout(60.0, read=300.0)

_RETRYABLE_CODES = {429, 500, 502, 503}


# ── Helpers ────────────────────────────────────────────────


def _retry(
    fn: Any,
    *,
    max_retries: int = 2,
    delay: float = 5.0,
    retryable_codes: set[int] | None = None,
) -> Any:
    """Execute *fn* with simple retry on transient HTTP errors."""
    codes = retryable_codes or _RETRYABLE_CODES
    last_exc: Exception | None = None
    for attempt in range(1 + max_retries):
        try:
            return fn()
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if exc.response.status_code not in codes:
                raise
            if attempt < max_retries:
                wait = delay * (2 ** attempt)
                logger.warning(
                    "Retryable HTTP %s for %s – retry %d after %.0fs",
                    exc.response.status_code,
                    exc.request.url,
                    attempt + 1,
                    wait,
                )
                time.sleep(wait)
        except (httpx.ConnectError, httpx.ReadTimeout) as exc:
            last_exc = exc
            if attempt < max_retries:
                wait = delay * (2 ** attempt)
                logger.warning(
                    "Network error %s – retry %d after %.0fs",
                    exc,
                    attempt + 1,
                    wait,
                )
                time.sleep(wait)
    raise last_exc  # type: ignore[misc]


def _image_to_data_uri(image_bytes: bytes, mime: str = "image/png") -> str:
    """Encode raw image bytes as a ``data:`` URI."""
    b64 = base64.b64encode(image_bytes).decode()
    return f"data:{mime};base64,{b64}"


# ── NovelAIClient ──────────────────────────────────────────


class NovelAIClient:
    """NovelAI V4.5 API client for anime full-body image generation."""

    def __init__(self) -> None:
        self._token = get_env_or_fail("NOVELAI_TOKEN", "image_gen")

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
    ) -> bytes:
        """Generate a full-body anime character image.

        Returns:
            PNG image bytes.
        """
        neg = negative_prompt or "lowres, bad anatomy"

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
            # V4/V4.5 structured prompt (required for nai-diffusion-4+)
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

        # Vibe Transfer
        if vibe_image is not None:
            b64 = base64.b64encode(vibe_image).decode()
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


# ── FluxKontextClient ──────────────────────────────────────


class FluxKontextClient:
    """Flux Kontext [pro] client via fal.ai for reference-based generation."""

    POLL_INTERVAL = 2.0  # seconds
    POLL_TIMEOUT = 120.0  # seconds

    def __init__(self) -> None:
        self._key = get_env_or_fail("FAL_KEY", "image_gen")

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

        # Submit task
        def _submit() -> str:
            resp = httpx.post(
                FAL_KONTEXT_SUBMIT_URL,
                json={"input": payload},
                headers=headers,
                timeout=_HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()["request_id"]

        request_id = _retry(_submit)

        # Poll for completion
        result_url = FAL_KONTEXT_RESULT_TPL.format(request_id=request_id)
        status_url = FAL_KONTEXT_STATUS_TPL.format(request_id=request_id)
        deadline = time.monotonic() + self.POLL_TIMEOUT

        while time.monotonic() < deadline:
            time.sleep(self.POLL_INTERVAL)
            status_resp = httpx.get(
                status_url, headers=headers, timeout=_HTTP_TIMEOUT,
            )
            status_resp.raise_for_status()
            status_data = status_resp.json()
            if status_data.get("status") == "COMPLETED":
                break
            if status_data.get("status") == "FAILED":
                raise RuntimeError(
                    f"Flux Kontext task {request_id} failed: "
                    f"{status_data.get('error', 'unknown')}"
                )
        else:
            raise TimeoutError(
                f"Flux Kontext task {request_id} timed out after "
                f"{self.POLL_TIMEOUT}s"
            )

        # Fetch result
        result_resp = httpx.get(
            result_url, headers=headers, timeout=_HTTP_TIMEOUT,
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


# ── MeshyClient ────────────────────────────────────────────


class MeshyClient:
    """Meshy Image-to-3D API client."""

    POLL_INTERVAL = 10.0  # seconds
    POLL_TIMEOUT = 600.0  # seconds (10 min)

    def __init__(self) -> None:
        self._key = get_env_or_fail("MESHY_API_KEY", "image_gen")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}"}

    def create_task(
        self,
        image_bytes: bytes,
        *,
        ai_model: str = "meshy-6",
        topology: str = "triangle",
        target_polycount: int = 30000,
        should_texture: bool = True,
        enable_pbr: bool = False,
    ) -> str:
        """Submit an image-to-3D task.

        Returns:
            Task ID string.
        """
        data_uri = _image_to_data_uri(image_bytes)
        body: dict[str, Any] = {
            "image_url": data_uri,
            "ai_model": ai_model,
            "topology": topology,
            "target_polycount": target_polycount,
            "should_texture": should_texture,
            "enable_pbr": enable_pbr,
        }

        def _call() -> str:
            resp = httpx.post(
                MESHY_IMAGE_TO_3D_URL,
                json=body,
                headers=self._headers(),
                timeout=_HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()["result"]

        return _retry(_call, max_retries=1, delay=10.0)

    def poll_task(self, task_id: str) -> dict[str, Any]:
        """Poll until task completes.

        Returns:
            Completed task dict with ``model_urls``.
        """
        url = MESHY_TASK_URL_TPL.format(task_id=task_id)
        deadline = time.monotonic() + self.POLL_TIMEOUT

        while time.monotonic() < deadline:
            resp = httpx.get(url, headers=self._headers(), timeout=_HTTP_TIMEOUT)
            resp.raise_for_status()
            task = resp.json()
            status = task.get("status", "")
            if status == "SUCCEEDED":
                return task
            if status in ("FAILED", "CANCELED"):
                err = task.get("task_error", {}).get("message", "unknown")
                raise RuntimeError(f"Meshy task {task_id} {status}: {err}")
            logger.debug(
                "Meshy task %s: %s (%d%%)",
                task_id, status, task.get("progress", 0),
            )
            time.sleep(self.POLL_INTERVAL)

        raise TimeoutError(
            f"Meshy task {task_id} timed out after {self.POLL_TIMEOUT}s"
        )

    def download_model(self, task: dict[str, Any], fmt: str = "glb") -> bytes:
        """Download the generated 3-D model.

        Args:
            task: Completed task dict (from :meth:`poll_task`).
            fmt: Model format key (``glb``, ``fbx``, ``obj``, ``usdz``).

        Returns:
            Raw model bytes.
        """
        model_urls = task.get("model_urls", {})
        url = model_urls.get(fmt)
        if not url:
            available = list(model_urls.keys())
            raise ValueError(
                f"Format '{fmt}' not available; got {available}"
            )
        resp = httpx.get(url, timeout=_DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        return resp.content

    def create_rigging_task(self, input_task_id: str) -> str:
        """Submit a rigging task for a completed image-to-3D task.

        Returns:
            Rigging task ID.
        """
        body = {"input_task_id": input_task_id}

        def _call() -> str:
            resp = httpx.post(
                MESHY_RIGGING_URL,
                json=body,
                headers=self._headers(),
                timeout=_HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()["result"]

        return _retry(_call, max_retries=1, delay=10.0)

    def poll_rigging_task(self, task_id: str) -> dict[str, Any]:
        """Poll until a rigging task completes."""
        url = MESHY_RIGGING_TASK_TPL.format(task_id=task_id)
        deadline = time.monotonic() + self.POLL_TIMEOUT

        while time.monotonic() < deadline:
            resp = httpx.get(url, headers=self._headers(), timeout=_HTTP_TIMEOUT)
            resp.raise_for_status()
            task = resp.json()
            status = task.get("status", "")
            if status == "SUCCEEDED":
                return task
            if status in ("FAILED", "CANCELED"):
                err = task.get("task_error", {}).get("message", "unknown")
                raise RuntimeError(f"Meshy rigging {task_id} {status}: {err}")
            time.sleep(self.POLL_INTERVAL)

        raise TimeoutError(
            f"Meshy rigging {task_id} timed out after {self.POLL_TIMEOUT}s"
        )


# ── PipelineResult ─────────────────────────────────────────


@dataclass
class PipelineResult:
    """Result of the full character asset generation pipeline."""

    fullbody_path: Path | None = None
    bustup_path: Path | None = None
    chibi_path: Path | None = None
    model_path: Path | None = None
    errors: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fullbody": str(self.fullbody_path) if self.fullbody_path else None,
            "bustup": str(self.bustup_path) if self.bustup_path else None,
            "chibi": str(self.chibi_path) if self.chibi_path else None,
            "model": str(self.model_path) if self.model_path else None,
            "errors": self.errors,
            "skipped": self.skipped,
        }


# ── ImageGenPipeline ───────────────────────────────────────


class ImageGenPipeline:
    """Orchestrates the full character asset generation pipeline.

    Steps:
      1. NovelAI V4.5 → full-body anime image
      2. Flux Kontext  → bust-up from reference  ─┐ independent
      3. Flux Kontext  → chibi from reference     ─┘
      4. Meshy Image-to-3D → GLB from chibi
    """

    ASSET_NAMES = {
        "fullbody": "avatar_fullbody.png",
        "bustup": "avatar_bustup.png",
        "chibi": "avatar_chibi.png",
        "model": "avatar_chibi.glb",
    }

    def __init__(self, person_dir: Path) -> None:
        self._person_dir = person_dir
        self._assets_dir = person_dir / "assets"

    def generate_all(
        self,
        prompt: str,
        negative_prompt: str = "",
        skip_existing: bool = True,
        steps: list[str] | None = None,
    ) -> PipelineResult:
        """Run the 4-step pipeline synchronously.

        Args:
            prompt: Character appearance tags for NovelAI.
            negative_prompt: Negative prompt for NovelAI.
            skip_existing: Skip steps whose output file already exists.
            steps: Subset of steps to run (default: all).

        Returns:
            PipelineResult with paths and error info.
        """
        self._assets_dir.mkdir(parents=True, exist_ok=True)
        enabled = set(steps) if steps else {"fullbody", "bustup", "chibi", "3d"}
        result = PipelineResult()

        # ── Step 1: Full-body ──
        fullbody_bytes: bytes | None = None
        fullbody_path = self._assets_dir / self.ASSET_NAMES["fullbody"]

        if "fullbody" in enabled:
            if skip_existing and fullbody_path.exists():
                result.skipped.append("fullbody")
                fullbody_bytes = fullbody_path.read_bytes()
                result.fullbody_path = fullbody_path
            else:
                try:
                    logger.info("Step 1: Generating full-body with NovelAI …")
                    client = NovelAIClient()
                    fullbody_bytes = client.generate_fullbody(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                    )
                    fullbody_path.write_bytes(fullbody_bytes)
                    result.fullbody_path = fullbody_path
                    logger.info("Step 1 complete: %s", fullbody_path)
                except Exception as exc:
                    result.errors.append(f"fullbody: {exc}")
                    logger.error("Step 1 failed: %s", exc)
        elif fullbody_path.exists():
            fullbody_bytes = fullbody_path.read_bytes()
            result.fullbody_path = fullbody_path

        if fullbody_bytes is None:
            # Cannot proceed without a reference image
            if not result.errors:
                result.errors.append(
                    "fullbody: No full-body image available as reference"
                )
            return result

        # ── Step 2 & 3: Bust-up and Chibi (sequential, same client) ──
        chibi_bytes: bytes | None = None

        if "bustup" in enabled:
            bustup_path = self._assets_dir / self.ASSET_NAMES["bustup"]
            if skip_existing and bustup_path.exists():
                result.skipped.append("bustup")
                result.bustup_path = bustup_path
            else:
                try:
                    logger.info("Step 2: Generating bust-up with Flux Kontext …")
                    kontext = FluxKontextClient()
                    bustup_bytes = kontext.generate_from_reference(
                        reference_image=fullbody_bytes,
                        prompt=_BUSTUP_PROMPT,
                        aspect_ratio="3:4",
                    )
                    bustup_path.write_bytes(bustup_bytes)
                    result.bustup_path = bustup_path
                    logger.info("Step 2 complete: %s", bustup_path)
                except Exception as exc:
                    result.errors.append(f"bustup: {exc}")
                    logger.error("Step 2 failed: %s", exc)

        if "chibi" in enabled:
            chibi_path = self._assets_dir / self.ASSET_NAMES["chibi"]
            if skip_existing and chibi_path.exists():
                result.skipped.append("chibi")
                chibi_bytes = chibi_path.read_bytes()
                result.chibi_path = chibi_path
            else:
                try:
                    logger.info("Step 3: Generating chibi with Flux Kontext …")
                    kontext = FluxKontextClient()
                    chibi_bytes = kontext.generate_from_reference(
                        reference_image=fullbody_bytes,
                        prompt=_CHIBI_PROMPT,
                        aspect_ratio="1:1",
                    )
                    chibi_path.write_bytes(chibi_bytes)
                    result.chibi_path = chibi_path
                    logger.info("Step 3 complete: %s", chibi_path)
                except Exception as exc:
                    result.errors.append(f"chibi: {exc}")
                    logger.error("Step 3 failed: %s", exc)

        # ── Step 4: 3-D model from chibi ──
        if "3d" in enabled:
            if chibi_bytes is None:
                chibi_path = self._assets_dir / self.ASSET_NAMES["chibi"]
                if chibi_path.exists():
                    chibi_bytes = chibi_path.read_bytes()

            model_path = self._assets_dir / self.ASSET_NAMES["model"]
            if skip_existing and model_path.exists():
                result.skipped.append("3d")
                result.model_path = model_path
            elif chibi_bytes is None:
                result.errors.append("3d: No chibi image available for 3D conversion")
            else:
                try:
                    logger.info("Step 4: Generating 3D model with Meshy …")
                    meshy = MeshyClient()
                    task_id = meshy.create_task(chibi_bytes)
                    logger.info("Meshy task created: %s", task_id)
                    task = meshy.poll_task(task_id)
                    glb_bytes = meshy.download_model(task, fmt="glb")
                    model_path.write_bytes(glb_bytes)
                    result.model_path = model_path
                    logger.info("Step 4 complete: %s", model_path)
                except Exception as exc:
                    result.errors.append(f"3d: {exc}")
                    logger.error("Step 4 failed: %s", exc)

        return result


# ── Tool Schemas ───────────────────────────────────────────


def get_tool_schemas() -> list[dict]:
    """Return Anthropic tool_use schemas for image generation tools."""
    return [
        {
            "name": "generate_character_assets",
            "description": (
                "Generate a complete set of character avatar assets: "
                "full-body image, bust-up image, chibi image, and a 3D model. "
                "Requires NOVELAI_TOKEN, FAL_KEY, and MESHY_API_KEY."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "Character appearance description using anime tags. "
                            "Example: '1girl, black hair, long hair, red eyes, "
                            "school uniform, full body, standing, white background'"
                        ),
                    },
                    "negative_prompt": {
                        "type": "string",
                        "description": "Things to avoid in the generated image.",
                        "default": "",
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["fullbody", "bustup", "chibi", "3d"],
                        },
                        "description": (
                            "Which pipeline steps to run. "
                            "Default: all four steps."
                        ),
                    },
                    "skip_existing": {
                        "type": "boolean",
                        "description": (
                            "If true, skip steps whose output file already exists."
                        ),
                        "default": True,
                    },
                },
                "required": ["prompt"],
            },
        },
        {
            "name": "generate_fullbody",
            "description": (
                "Generate an anime full-body character image using NovelAI V4.5. "
                "Saves to assets/avatar_fullbody.png. "
                "Requires NOVELAI_TOKEN."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Character appearance tags for NovelAI.",
                    },
                    "negative_prompt": {
                        "type": "string",
                        "description": "Negative prompt.",
                        "default": "",
                    },
                    "width": {
                        "type": "integer",
                        "description": "Image width in pixels.",
                        "default": 1024,
                    },
                    "height": {
                        "type": "integer",
                        "description": "Image height in pixels.",
                        "default": 1536,
                    },
                    "seed": {
                        "type": "integer",
                        "description": "Seed for reproducibility.",
                    },
                },
                "required": ["prompt"],
            },
        },
        {
            "name": "generate_bustup",
            "description": (
                "Generate a bust-up portrait from a reference image "
                "using Flux Kontext [pro]. Saves to assets/avatar_bustup.png. "
                "Requires FAL_KEY and an existing full-body image."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "Bust-up generation prompt. "
                            "A default prompt is used if omitted."
                        ),
                    },
                },
                "required": [],
            },
        },
        {
            "name": "generate_chibi",
            "description": (
                "Generate a chibi / super-deformed version from a reference "
                "image using Flux Kontext [pro]. Saves to assets/avatar_chibi.png. "
                "Requires FAL_KEY and an existing full-body image."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "Chibi generation prompt. "
                            "A default prompt is used if omitted."
                        ),
                    },
                },
                "required": [],
            },
        },
        {
            "name": "generate_3d_model",
            "description": (
                "Generate a 3D model (GLB) from a chibi image using "
                "Meshy Image-to-3D. Saves to assets/avatar_chibi.glb. "
                "Requires MESHY_API_KEY and an existing chibi image."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "ai_model": {
                        "type": "string",
                        "description": "Meshy model version.",
                        "default": "meshy-6",
                        "enum": ["meshy-5", "meshy-6"],
                    },
                    "target_polycount": {
                        "type": "integer",
                        "description": "Target polygon count.",
                        "default": 30000,
                    },
                },
                "required": [],
            },
        },
    ]


# ── CLI entry point ────────────────────────────────────────


def cli_main(argv: list[str] | None = None) -> None:
    """CLI entry point for ``animaworks-tool image_gen``."""
    parser = argparse.ArgumentParser(
        description="Character image & 3D model generation",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- pipeline --
    p_pipe = sub.add_parser("pipeline", help="Run full 4-step pipeline")
    p_pipe.add_argument("prompt", help="Character appearance tags")
    p_pipe.add_argument("-n", "--negative", default="", help="Negative prompt")
    p_pipe.add_argument(
        "-d", "--person-dir", required=True, help="Person data directory",
    )
    p_pipe.add_argument(
        "--steps", nargs="*",
        choices=["fullbody", "bustup", "chibi", "3d"],
        help="Steps to run (default: all)",
    )
    p_pipe.add_argument(
        "--no-skip", action="store_true", help="Regenerate even if files exist",
    )
    p_pipe.add_argument("-j", "--json", action="store_true", help="JSON output")

    # -- fullbody --
    p_full = sub.add_parser("fullbody", help="Generate full-body image only")
    p_full.add_argument("prompt", help="Character appearance tags")
    p_full.add_argument("-n", "--negative", default="", help="Negative prompt")
    p_full.add_argument("-o", "--output", default="avatar_fullbody.png")
    p_full.add_argument("-W", "--width", type=int, default=1024)
    p_full.add_argument("-H", "--height", type=int, default=1536)
    p_full.add_argument("-s", "--seed", type=int, default=None)
    p_full.add_argument("-j", "--json", action="store_true")

    # -- bustup --
    p_bust = sub.add_parser("bustup", help="Generate bust-up from reference")
    p_bust.add_argument("reference", help="Path to reference image")
    p_bust.add_argument("-p", "--prompt", default=_BUSTUP_PROMPT)
    p_bust.add_argument("-o", "--output", default="avatar_bustup.png")
    p_bust.add_argument("-j", "--json", action="store_true")

    # -- chibi --
    p_chibi = sub.add_parser("chibi", help="Generate chibi from reference")
    p_chibi.add_argument("reference", help="Path to reference image")
    p_chibi.add_argument("-p", "--prompt", default=_CHIBI_PROMPT)
    p_chibi.add_argument("-o", "--output", default="avatar_chibi.png")
    p_chibi.add_argument("-j", "--json", action="store_true")

    # -- 3d --
    p_3d = sub.add_parser("3d", help="Generate 3D model from image")
    p_3d.add_argument("image", help="Path to input image")
    p_3d.add_argument("-o", "--output", default="avatar_chibi.glb")
    p_3d.add_argument("--ai-model", default="meshy-6")
    p_3d.add_argument("--polycount", type=int, default=30000)
    p_3d.add_argument("-j", "--json", action="store_true")

    args = parser.parse_args(argv)

    # ── Execute ────────────────────────────────────────────

    if args.command == "pipeline":
        pipe = ImageGenPipeline(Path(args.person_dir))
        result = pipe.generate_all(
            prompt=args.prompt,
            negative_prompt=args.negative,
            skip_existing=not args.no_skip,
            steps=args.steps,
        )
        if args.json:
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            for k, v in result.to_dict().items():
                print(f"{k}: {v}")

    elif args.command == "fullbody":
        client = NovelAIClient()
        img = client.generate_fullbody(
            prompt=args.prompt,
            negative_prompt=args.negative,
            width=args.width,
            height=args.height,
            seed=args.seed,
        )
        Path(args.output).write_bytes(img)
        out = {"output": args.output, "size": len(img)}
        if args.json:
            print(json.dumps(out))
        else:
            print(f"Saved: {args.output} ({len(img)} bytes)")

    elif args.command == "bustup":
        ref_bytes = Path(args.reference).read_bytes()
        client = FluxKontextClient()
        img = client.generate_from_reference(
            reference_image=ref_bytes,
            prompt=args.prompt,
            aspect_ratio="3:4",
        )
        Path(args.output).write_bytes(img)
        out = {"output": args.output, "size": len(img)}
        if args.json:
            print(json.dumps(out))
        else:
            print(f"Saved: {args.output} ({len(img)} bytes)")

    elif args.command == "chibi":
        ref_bytes = Path(args.reference).read_bytes()
        client = FluxKontextClient()
        img = client.generate_from_reference(
            reference_image=ref_bytes,
            prompt=args.prompt,
            aspect_ratio="1:1",
        )
        Path(args.output).write_bytes(img)
        out = {"output": args.output, "size": len(img)}
        if args.json:
            print(json.dumps(out))
        else:
            print(f"Saved: {args.output} ({len(img)} bytes)")

    elif args.command == "3d":
        img_bytes = Path(args.image).read_bytes()
        client = MeshyClient()
        task_id = client.create_task(
            img_bytes, ai_model=args.ai_model, target_polycount=args.polycount,
        )
        print(f"Meshy task: {task_id}", file=sys.stderr)
        task = client.poll_task(task_id)
        glb = client.download_model(task, fmt="glb")
        Path(args.output).write_bytes(glb)
        out = {"output": args.output, "size": len(glb), "task_id": task_id}
        if args.json:
            print(json.dumps(out))
        else:
            print(f"Saved: {args.output} ({len(glb)} bytes)")
