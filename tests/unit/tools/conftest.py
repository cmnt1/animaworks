# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Fixtures for tools unit tests.

Disable codex-first selection by default so existing image-gen tests that
patch NovelAI/Flux clients keep working on machines where codex is installed.
Individual tests can re-enable via monkeypatch.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_codex_image_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.tools.image_gen.codex_available", lambda: False)
    monkeypatch.setattr("core.tools.image.codex.codex_available", lambda: False)
