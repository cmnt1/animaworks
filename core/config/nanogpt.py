"""Read nanoGPT credentials from the local source on each request."""

from __future__ import annotations

import ast
import os
from pathlib import Path

NANOGPT_SECRETS_PATH_ENV = "ANIMAWORKS_NANOGPT_SECRETS_PATH"
_DEFAULT_ABCONFIG_DIR = Path("E:/OneDriveBiz/Tools/abconfig")


def nanogpt_api_key(configured: str | None = None) -> str:
    """Prefer local ``nanogpt_api`` over a potentially stale configured key.

    Read the source without importing it or caching Python bytecode, so key
    rotation takes effect on the next request. Only a literal string assignment
    is supported; unrelated code and secrets in the file are never executed.
    An existing but invalid source fails closed instead of retrying an old key.

    The explicit path is authoritative. Otherwise use ``secrets_local.py``
    next to Cnct_Env.py.
    Deployments without these files retain config/environment resolution.
    """
    explicit = os.environ.get(NANOGPT_SECRETS_PATH_ENV)
    bridge = os.environ.get("ANIMAWORKS_ABCONFIG_PATH")
    base = Path(bridge).parent if bridge else _DEFAULT_ABCONFIG_DIR
    paths = [Path(explicit)] if explicit else [base / "secrets_local.py"]
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            if not explicit:
                continue
            raise ValueError(f"nanoGPT secrets file not found: {path}") from None
        except OSError:
            raise ValueError(f"Cannot read nanoGPT secrets file: {path}") from None
        try:
            tree = ast.parse(source)
            value = None
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, ast.AnnAssign):
                    targets = [node.target]
                else:
                    continue
                if any(isinstance(target, ast.Name) and target.id == "nanogpt_api" for target in targets):
                    value = ast.literal_eval(node.value)
            if isinstance(value, str) and value.strip():
                return value.strip()
        except (SyntaxError, ValueError, TypeError):
            pass
        # Do not include parser errors: their source lines may contain secrets.
        raise ValueError(f"nanoGPT secrets file must define a non-empty literal nanogpt_api: {path}") from None
    return configured or os.environ.get("NANOGPT_API_KEY", "")
