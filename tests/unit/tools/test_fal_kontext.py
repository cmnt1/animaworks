"""Unit tests for FluxKontextClient (fal-ai/flux-pro/kontext) in core/tools/image/fal.py."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.tools._base import ToolConfigError
from core.tools.image.constants import FAL_KONTEXT_SUBMIT_URL
from core.tools.image.fal import FluxKontextClient


class TestFluxKontextClientInit:
    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

    def test_requires_fal_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("FAL_KEY", raising=False)
        with pytest.raises(ToolConfigError):
            FluxKontextClient()

    def test_reads_fal_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FAL_KEY", "kontext-key")
        client = FluxKontextClient()
        assert client._key == "kontext-key"


class TestFluxKontextSubmitPayload:
    """Kontext OpenAPI uses aspect_ratio; do not send undocumented image_size."""

    @pytest.fixture(autouse=True)
    def _set_key(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("FAL_KEY", "test-fal-key")

    def _make_submit_response(self, request_id: str = "req-k"):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "request_id": request_id,
            "status_url": f"https://queue.fal.run/status/{request_id}",
            "response_url": f"https://queue.fal.run/result/{request_id}",
        }
        return resp

    def _make_status_response(self, status: str = "COMPLETED"):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"status": status}
        return resp

    def _make_result_response(self, image_url: str = "https://cdn.fal.ai/out.png"):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"images": [{"url": image_url}]}
        return resp

    def _make_image_response(self, content: bytes = b"OUT"):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.content = content
        return resp

    def test_submit_json_has_aspect_ratio_not_image_size(self):
        client = FluxKontextClient()
        ref = b"\x89PNG\r\n\x1a\ntiny"

        submit_resp = self._make_submit_response()
        status_resp = self._make_status_response("COMPLETED")
        result_resp = self._make_result_response()
        image_resp = self._make_image_response()

        with (
            patch("core.tools.image.fal.httpx.post", return_value=submit_resp) as mock_post,
            patch(
                "core.tools.image.fal.httpx.get",
                side_effect=[status_resp, result_resp, image_resp],
            ),
            patch("core.tools.image.fal.time.sleep"),
        ):
            client.generate_from_reference(
                reference_image=ref,
                prompt="edit this",
                aspect_ratio="1:1",
                guidance_scale=4.0,
                seed=99,
            )

        assert mock_post.call_count >= 1
        kontext_post = [c for c in mock_post.call_args_list if c[0][0] == FAL_KONTEXT_SUBMIT_URL]
        assert len(kontext_post) == 1
        payload = kontext_post[0][1]["json"]
        assert payload["aspect_ratio"] == "1:1"
        assert payload["guidance_scale"] == 4.0
        assert payload["seed"] == 99
        assert "image_size" not in payload
        assert "image_url" in payload
        assert payload["image_url"].startswith("data:")

    def test_seed_omitted_when_none(self):
        client = FluxKontextClient()
        ref = b"\x89PNG\r\n\x1a\nx"

        submit_resp = self._make_submit_response()
        status_resp = self._make_status_response("COMPLETED")
        result_resp = self._make_result_response()
        image_resp = self._make_image_response()

        with (
            patch("core.tools.image.fal.httpx.post", return_value=submit_resp) as mock_post,
            patch(
                "core.tools.image.fal.httpx.get",
                side_effect=[status_resp, result_resp, image_resp],
            ),
            patch("core.tools.image.fal.time.sleep"),
        ):
            client.generate_from_reference(ref, prompt="x", seed=None)

        kontext_post = [c for c in mock_post.call_args_list if c[0][0] == FAL_KONTEXT_SUBMIT_URL]
        payload = kontext_post[0][1]["json"]
        assert "seed" not in payload
