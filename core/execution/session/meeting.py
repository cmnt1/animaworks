from __future__ import annotations

"""Meeting context shared with tool subprocesses."""

import contextvars
from typing import Any

meeting_mode: contextvars.ContextVar[bool] = contextvars.ContextVar("meeting_mode", default=False)
meeting_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("meeting_context", default=None)
