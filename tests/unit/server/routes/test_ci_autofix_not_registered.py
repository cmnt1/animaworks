from __future__ import annotations

from pathlib import Path


def test_ci_autofix_routes_are_not_registered_on_animaworks_app() -> None:
    routes_init = Path("server/routes/__init__.py").read_text(encoding="utf-8")

    assert "server.routes.ci_autofix" not in routes_init
    assert "create_ci_autofix_api_router" not in routes_init
    assert "create_ci_autofix_page_router" not in routes_init
