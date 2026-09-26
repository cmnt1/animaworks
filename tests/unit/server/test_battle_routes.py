"""Battle HTML uses the production route and base-path/version injection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.auth.models import AuthConfig
from core.config.models import AnimaWorksConfig


@pytest.mark.parametrize("prefix", ["", "/office"])
async def test_battle_routes_and_assets(tmp_path, monkeypatch, prefix):
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
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for path in ["/battle", "/battle/"]:
                response = await client.get(prefix + path)
                assert response.status_code == 200
                assert response.headers["cache-control"] == "no-store"
                assert f'content="{prefix}"' in response.text
                assert "__AW_BASE__" not in response.text
                assert "__AW_VERSION__" not in response.text
                assert 'id="battle"' in response.text
                import re

                script = re.search(r'src="([^"]+/battle/modules/app.js)"', response.text).group(1)
                asset = await client.get(script)
                assert asset.status_code == 200
                assert "BattleLiveClient" in asset.text
            for path in ["/battle/assets/moonlit-ruins.png", "/battle/assets/combatants.png"]:
                asset = await client.get(prefix + path)
                assert asset.status_code == 200
                assert asset.headers["content-type"] == "image/png"
            pixel = await client.get(prefix + "/workspace/pixel/")
            assert pixel.status_code == 200
            assert "workspace" in pixel.text
