# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Windows stdin line reader that never leaves a blocking ReadFile pending.

The MCP SDK's default stdin reads lines in a worker thread.  On Windows a
synchronous ReadFile pending on the stdin pipe blocks loading C-extension
DLLs (numpy, chromadb, ...) in any other thread, so the first tool call that
triggers such an import stalls until the client sends another message.
This reader polls ``PeekNamedPipe`` and only reads bytes already buffered.
"""

from __future__ import annotations

import codecs
import ctypes
import os
import sys
from collections.abc import AsyncIterator
from ctypes import wintypes

import anyio

_POLL_INTERVAL_S = 0.01
_CHUNK = 65536


def _peek_available(handle: int) -> int | None:
    """Bytes waiting in the pipe, or ``None`` once the writer has closed it."""
    avail = wintypes.DWORD(0)
    ok = ctypes.windll.kernel32.PeekNamedPipe(  # type: ignore[attr-defined]
        wintypes.HANDLE(handle), None, 0, None, ctypes.byref(avail), None
    )
    return avail.value if ok else None


def open_pipe_stdin() -> AsyncIterator[str] | None:
    """Return a polling line reader for a piped stdin, or ``None`` if stdin is not a pipe."""
    import msvcrt

    fd = sys.stdin.fileno()
    handle = msvcrt.get_osfhandle(fd)
    if _peek_available(handle) is None:
        return None
    return _read_lines(fd, handle)


async def _read_lines(fd: int, handle: int) -> AsyncIterator[str]:
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    buf = ""
    while True:
        avail = _peek_available(handle)
        if avail is None:
            break
        if avail == 0:
            await anyio.sleep(_POLL_INTERVAL_S)
            continue
        buf += decoder.decode(os.read(fd, min(avail, _CHUNK)))
        *lines, buf = buf.split("\n")
        for line in lines:
            yield line + "\n"
    buf += decoder.decode(b"", final=True)
    if buf:
        yield buf
