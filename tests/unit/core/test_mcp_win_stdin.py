"""Tests for core.mcp.win_stdin — the non-blocking Windows stdin line reader."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from unittest.mock import patch

import pytest

from core.mcp import win_stdin


class TestReadLines:
    async def test_splits_lines_across_chunks_and_flushes_tail_at_eof(self) -> None:
        # Multi-byte UTF-8 ("あ" = e3 81 82) split across reads must decode intact.
        chunks = [b'{"a":1}\n{"b":"\xe3\x81', b'\x82"}\n{"c"', b":3}"]
        avail = [0, len(chunks[0]), len(chunks[1]), len(chunks[2]), None]

        with (
            patch.object(win_stdin, "_peek_available", side_effect=avail),
            patch.object(win_stdin.os, "read", side_effect=chunks),
            patch.object(win_stdin, "_POLL_INTERVAL_S", 0),
        ):
            lines = [line async for line in win_stdin._read_lines(0, 0)]

        assert lines == ['{"a":1}\n', '{"b":"あ"}\n', '{"c":3}']


@pytest.mark.skipif(sys.platform != "win32", reason="Windows pipe semantics")
def test_numpy_import_does_not_stall_while_reader_waits() -> None:
    """A pending blocking stdin read stalls numpy's DLL load; the peek reader must not."""
    child = textwrap.dedent(
        """
        import threading, time, anyio
        from core.mcp.win_stdin import open_pipe_stdin

        async def main():
            stdin = open_pipe_stdin()
            assert stdin is not None
            async with anyio.create_task_group() as tg:
                async def drain():
                    async for _ in stdin:
                        pass
                tg.start_soon(drain)
                await anyio.sleep(0.3)
                await anyio.to_thread.run_sync(__import__, "numpy")
                print("imported", flush=True)
                tg.cancel_scope.cancel()

        anyio.run(main)
        """
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", child],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": os.getcwd()},
        text=True,
    )
    try:
        out = proc.stdout.readline()  # stdin stays open: no EOF to unblock a read
    finally:
        proc.kill()
    assert out.strip() == "imported"
