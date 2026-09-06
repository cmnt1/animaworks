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
    resume = getattr(args, "resume", None)

    client = AnimaWorksClient(base_url, from_person=from_person)

    # Resolve the session (resume vs. new).
    from cli.tui.session import (
        SessionInfo,
        latest_session,
        load_session,
        new_session,
    )

    session: SessionInfo | None = None
    if resume:
        sid = None if resume == "latest" else resume
        session = latest_session() if sid is None else load_session(sid)
        if session is None:
            print("no session to resume", file=__import__("sys").stderr)
            __import__("sys").exit(1)
        if getattr(args, "anima", None):
            session.anima = args.anima  # positional anima wins

    if session is None:
        session = new_session(
            anima=args.anima,
            thread_id=thread_id,
            gateway_url=base_url,
            from_person=from_person,
        )

    # Authenticate before starting the TUI (only when required).
    if not _maybe_login(client, args):
        __import__("sys").exit(1)

    app = AnimaChatApp(
        client=client,
        anima_name=session.anima,
        thread_id=session.thread_id,
        session=session,
        no_reattach=getattr(args, "no_reattach", False),
    )
    app.run()


def _maybe_login(client, args) -> bool:
    """Authenticate the client if the gateway requires it.

    Returns True when we are ready to proceed (already authenticated,
    login succeeded, or auth is disabled).
    """
    import getpass as _getpass
    import os
    import sys

    try:
        me = client.auth_me()
    except Exception:
        # Connection issues surface later in the TUI; proceed unauthenticated.
        return True
    if me is not None:
        return True  # already authenticated (or auth disabled)

    username = getattr(args, "user", None)
    if not username:
        try:
            username = input("Username: ")
        except EOFError:
            print("Login required but no username given", file=sys.stderr)
            return False
    password = getattr(args, "password", None) or os.environ.get("ANIMAWORKS_TUI_PASSWORD")
    if password is None:
        try:
            password = _getpass.getpass("Password: ")
        except EOFError:
            print("Login required but no password given", file=sys.stderr)
            return False
    try:
        client.login(username, password)
    except Exception as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        return False
    return True
