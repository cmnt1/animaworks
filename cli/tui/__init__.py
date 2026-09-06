# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse


def run_tui(args: argparse.Namespace) -> None:
    """Launch the interactive terminal chat UI.

    Resolves the gateway URL, builds an ``AnimaWorksClient`` and runs the
    Textual app. Exits with a helpful message when Textual (or one of its
    peer dependencies) is not installed.
    """
    from cli.tui.app import AnimaChatApp
    from cli.tui.client import AnimaWorksClient

    try:
        import textual  # noqa: F401
        import websockets  # noqa: F401
    except ImportError:
        print(
            "The TUI requires the optional 'tui' extra (textual, websockets).\n"
            'Install it with:  pip install "animaworks[tui]"   (or)   uv sync --extra tui',
            file=__import__("sys").stderr,
        )
        __import__("sys").exit(1)

    from cli._gateway import resolve_gateway_url

    base_url = resolve_gateway_url(args)
    thread_id = getattr(args, "thread_id", "default") or "default"
    from_person = getattr(args, "from_person", "human") or "human"

    client = AnimaWorksClient(base_url, from_person=from_person)
    app = AnimaChatApp(
        client=client,
        anima_name=args.anima,
        thread_id=thread_id,
    )
    app.run()
