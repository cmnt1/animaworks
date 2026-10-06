"""The standalone pixel route is retained only for explicit mock previews."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.auth.models import AuthConfig
from core.config.models import AnimaWorksConfig


@pytest.mark.parametrize("prefix", ["", "/office"])
async def test_pixel_workspace_redirects_to_shell_unless_mock_is_present(
    tmp_path, monkeypatch, prefix
):
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    config = AnimaWorksConfig(setup_complete=True)
    config.server.base_path = prefix
    with (
        patch("server.app.load_config", return_value=config),
        patch("server.app.load_auth", return_value=AuthConfig(auth_mode="local_trust")),
        patch("server.app.ProcessSupervisor", return_value=MagicMock()),
    ):
        from server.app import create_app

        app = create_app(tmp_path / "animas", tmp_path / "shared")
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            for path in ["/workspace/pixel", "/workspace/pixel/"]:
                response = await client.get(prefix + path)
                assert response.status_code in (302, 307)
                assert response.headers["location"] == prefix + "/workspace/?renderer=pixel"

            preview = await client.get(prefix + "/workspace/pixel/?mock=1")
            assert preview.status_code == 200
            assert 'id="stage"' in preview.text
            assert 'id="workspace"' in preview.text
            assert "__AW_BASE__" not in preview.text
            assert "__AW_VERSION__" not in preview.text
