from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Shared CLI utilities for messaging tool CLIs (Slack, Chatwork).

Provides common argparse patterns, output formatting, and error
handling used by both ``slack_cli`` and ``chatwork_cli``.
"""

import json
import sys
from collections.abc import Callable
from functools import wraps
from typing import Any


def print_json(data: Any) -> None:
    """Print data as pretty-printed JSON to stdout."""
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def cli_main_safely(func: Callable[..., Any]) -> Callable[..., None]:
    """Wrap a CLI entry point with :func:`run_cli_safely` error handling."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        run_cli_safely(lambda: func(*args, **kwargs))

    return wrapper


def run_cli_safely(
    func: Any,
    *,
    api_error_type: type | None = None,
) -> None:
    """Run a CLI dispatch function with standard error handling.

    Catches ``api_error_type`` (if given), ``KeyboardInterrupt``, and
    generic exceptions, printing user-friendly messages to stderr.
    """
    try:
        func()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as e:
        if api_error_type and isinstance(e, api_error_type):
            error = getattr(e, "response", {})
            if isinstance(error, dict):
                error = error.get("error", str(e))
            print(f"API error: {error}", file=sys.stderr)
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
