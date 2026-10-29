from __future__ import annotations

import pytest


def test_claude_sdk_patch_is_applied_by_package_import() -> None:
    pytest.importorskip("claude_agent_sdk")

    import core.execution.engines.claude._sdk_session  # noqa: F401
    from core.execution.engines.claude import _sdk_patch

    assert _sdk_patch._patched is True
