from __future__ import annotations

"""Build the shared environment passed to AnimaWorks MCP subprocesses."""

import os
from pathlib import Path

from core.paths import PROJECT_DIR
from core.platform.env import get_env, server_url_env

# Without these URLs MCP children may load SentenceTransformer/CrossEncoder
# models locally instead of using the root-owned services.
_MCP_SERVICE_ENV_KEYS = (
    "ANIMAWORKS_EMBED_URL",
    "ANIMAWORKS_VECTOR_URL",
    "ANIMAWORKS_RERANK_URL",
    "ANIMAWORKS_INTERNAL_AUTH",
)


def build_mcp_env(anima_dir: Path) -> dict[str, str]:
    """Return the common environment required by every engine's MCP server."""
    env = {
        "ANIMAWORKS_ANIMA_DIR": str(anima_dir),
        "ANIMAWORKS_PROJECT_DIR": str(PROJECT_DIR),
        "PYTHONPATH": str(PROJECT_DIR),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }
    env.update(server_url_env())
    for name in _MCP_SERVICE_ENV_KEYS:
        if value := get_env(name):
            env[name] = value

    from core.execution.session.session_context import current_runtime_session

    runtime_ctx = current_runtime_session()
    if runtime_ctx is not None:
        env.update(runtime_ctx.to_env())
    return env
