# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Meshy Image-to-3D, Rigging, and Animation API client."""

from __future__ import annotations

import time
from typing import Any

import httpx

from core.tools._base import get_credential, logger

from .constants import (
    _DOWNLOAD_TIMEOUT,
    _HTTP_TIMEOUT,
    MESHY_ANIMATION_TASK_TPL,
    MESHY_ANIMATION_URL,
    MESHY_IMAGE_TO_3D_URL,
    MESHY_RIGGING_TASK_TPL,
    MESHY_RIGGING_URL,
    MESHY_TASK_URL_TPL,
)
from .utils import _image_to_data_uri, _retry


class MeshyClient:
    """Meshy Image-to-3D API client."""

    POLL_INTERVAL = 10.0  # seconds
    POLL_TIMEOUT = 600.0  # seconds (10 min)

    def __init__(self) -> None:
        self._key = get_credential("meshy", "image_gen", env_var="MESHY_API_KEY")

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
                task_id,
                status,
                task.get("progress", 0),
            )
            time.sleep(self.POLL_INTERVAL)

        raise TimeoutError(f"Meshy task {task_id} timed out after {self.POLL_TIMEOUT}s")

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
            raise ValueError(f"Format '{fmt}' not available; got {available}")
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

    def create_rigging_task_from_glb(
        self,
        glb_bytes: bytes,
        *,
        height_meters: float = 1.0,
    ) -> str:
        """Submit a rigging task using a GLB ``model_url`` (data URI).

        Used when no image-to-3D ``input_task_id`` is available (e.g. animations-only regen).
        """
        data_uri = _image_to_data_uri(glb_bytes, mime="model/gltf-binary")
        body: dict[str, Any] = {
            "model_url": data_uri,
            "height_meters": height_meters,
        }

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
            logger.debug(
                "Meshy rigging %s: %s (%d%%)",
                task_id,
                status,
                task.get("progress", 0),
            )
            time.sleep(self.POLL_INTERVAL)

        raise TimeoutError(f"Meshy rigging {task_id} timed out after {self.POLL_TIMEOUT}s")

    def download_rigged_model(self, task: dict[str, Any], fmt: str = "glb") -> bytes:
        """Download the rigged character model.

        Args:
            task: Completed rigging task dict.
            fmt: Format (``glb`` or ``fbx``).

        Returns:
            Raw model bytes.
        """
        result = task.get("result", {})
        key = f"rigged_character_{fmt}_url"
        url = result.get(key)
        if not url:
            raise ValueError(f"Rigging result missing '{key}'")
        resp = httpx.get(url, timeout=_DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        return resp.content

    def download_rigging_animations(self, task: dict[str, Any]) -> dict[str, bytes]:
        """Download built-in walking/running animations from rigging task.

        Prefers armature-only GLBs (skeleton + animation, no mesh) when
        available.  Falls back to full model GLBs.

        Returns:
            Dict mapping animation name to GLB bytes.
        """
        result = task.get("result", {})
        basic = result.get("basic_animations", {})
        animations: dict[str, bytes] = {}
        for name in ("walking", "running"):
            url = basic.get(f"{name}_armature_glb_url") or basic.get(f"{name}_glb_url")
            if url:
                logger.debug("Downloading %s animation …", name)
                resp = httpx.get(url, timeout=_DOWNLOAD_TIMEOUT)
                resp.raise_for_status()
                animations[name] = resp.content
        return animations

    def create_animation_task(self, rig_task_id: str, action_id: int) -> str:
        """Submit an animation task for a rigged character.

        Args:
            rig_task_id: Completed rigging task ID.
            action_id: Animation preset ID (see Meshy animation library).

        Returns:
            Animation task ID.
        """
        body: dict[str, Any] = {
            "rig_task_id": rig_task_id,
            "action_id": action_id,
            "post_process": {"operation_type": "extract_armature"},
        }

        def _call() -> str:
            resp = httpx.post(
                MESHY_ANIMATION_URL,
                json=body,
                headers=self._headers(),
                timeout=_HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()["result"]

        return _retry(_call, max_retries=1, delay=10.0)

    def poll_animation_task(self, task_id: str) -> dict[str, Any]:
        """Poll until an animation task completes."""
        url = MESHY_ANIMATION_TASK_TPL.format(task_id=task_id)
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
                raise RuntimeError(f"Meshy animation {task_id} {status}: {err}")
            logger.debug(
                "Meshy animation %s: %s (%d%%)",
                task_id,
                status,
                task.get("progress", 0),
            )
            time.sleep(self.POLL_INTERVAL)

        raise TimeoutError(f"Meshy animation {task_id} timed out after {self.POLL_TIMEOUT}s")

    def download_animation(self, task: dict[str, Any], fmt: str = "glb") -> bytes:
        """Download generated animation file.

        Args:
            task: Completed animation task dict.
            fmt: Format (``glb`` or ``fbx``).

        Returns:
            Raw animation bytes.
        """
        result = task.get("result", {})
        url = result.get(f"animation_{fmt}_url")
        if not url:
            raise ValueError(f"Animation result missing 'animation_{fmt}_url'")
        resp = httpx.get(url, timeout=_DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        return resp.content
