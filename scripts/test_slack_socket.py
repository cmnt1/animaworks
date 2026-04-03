"""Minimal Slack Socket Mode test — bypasses AnimaWorks entirely.

Usage:
    .venv/Scripts/python.exe scripts/test_slack_socket.py

Reads SLACK_BOT_TOKEN__ayane and SLACK_APP_TOKEN__ayane from .env,
connects via Socket Mode, and prints every event received.
Press Ctrl+C to stop.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# Load .env
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and val:
            os.environ.setdefault(key, val)

# Enable verbose logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from slack_bolt.app.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN__ayane", "")
APP_TOKEN = os.environ.get("SLACK_APP_TOKEN__ayane", "")

if not BOT_TOKEN or not APP_TOKEN:
    print("ERROR: SLACK_BOT_TOKEN__ayane and SLACK_APP_TOKEN__ayane must be set in .env")
    sys.exit(1)

print(f"Bot token: {BOT_TOKEN[:15]}...")
print(f"App token: {APP_TOKEN[:15]}...")


async def main():
    app = AsyncApp(token=BOT_TOKEN)

    @app.event("message")
    async def on_message(event, say):
        print(f"\n{'='*60}")
        print(f"MESSAGE EVENT: {event}")
        print(f"{'='*60}\n")

    @app.event("app_mention")
    async def on_mention(event, say):
        print(f"\n{'='*60}")
        print(f"APP_MENTION EVENT: {event}")
        print(f"{'='*60}\n")

    @app.event({"type": "message", "subtype": "bot_message"})
    async def on_bot_message(event, say):
        print(f"\n{'='*60}")
        print(f"BOT_MESSAGE EVENT: {event}")
        print(f"{'='*60}\n")

    handler = AsyncSocketModeHandler(app, APP_TOKEN)

    # Add raw listener
    def raw_listener(req):
        print(f"\n>>> RAW SOCKET MODE REQUEST: type={req.type} envelope_id={req.envelope_id}")
        if hasattr(req, "payload"):
            import json
            try:
                print(f"    payload keys: {list(req.payload.keys()) if isinstance(req.payload, dict) else type(req.payload)}")
            except Exception:
                pass

    handler.client.socket_mode_request_listeners.append(raw_listener)

    print("\nConnecting to Slack Socket Mode...")
    await handler.connect_async()
    print("Connected! Waiting for events... (send a message in Slack, then check here)")
    print("Press Ctrl+C to stop.\n")

    # Keep alive
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        await handler.close_async()


if __name__ == "__main__":
    asyncio.run(main())
