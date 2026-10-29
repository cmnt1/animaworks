from __future__ import annotations

import asyncio
import sys

import pytest

from core.execution.process_runner import ProcessRunner


@pytest.mark.asyncio
async def test_process_runner_drains_stderr_while_child_is_running() -> None:
    runner = ProcessRunner()
    process = await runner.start(
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('x' * 200000); sys.stderr.flush(); print('done')",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        assert process.stdout is not None
        assert await asyncio.wait_for(process.stdout.readline(), timeout=5) == b"done\n"
        assert await process.wait() == 0
        assert len(await runner.stderr()) == 200000
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_process_runner_terminates_child_process() -> None:
    runner = ProcessRunner(graceful_timeout=0.1)
    process = await runner.start(
        sys.executable,
        "-c",
        "import time; time.sleep(60)",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    await runner.close()

    assert process.returncode is not None
