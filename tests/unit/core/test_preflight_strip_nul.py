from __future__ import annotations

import pytest

from core.agent.priming import PrimingMixin


@pytest.mark.asyncio
async def test_preflight_strips_nul_bytes() -> None:
    system_prompt, prompt = await PrimingMixin()._preflight_size_check(
        "state line\n" + "\x00" * 629,
        "hello\x00",
        None,
        priming_section="",
        mode="s",
        message="hello",
    )

    assert system_prompt == "state line\n"
    assert prompt == "hello"


@pytest.mark.asyncio
async def test_preflight_keeps_clean_prompt() -> None:
    result = await PrimingMixin()._preflight_size_check(
        "system", "prompt", None, priming_section="", mode="s", message="prompt"
    )

    assert result == ("system", "prompt")
