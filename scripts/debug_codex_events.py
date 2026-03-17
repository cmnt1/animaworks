#!/usr/bin/env python3
"""Directly call Codex SDK and log every raw event with timing.

Uses the same environment/credentials as the kaede runner.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def main(anima_name: str, message: str) -> None:
    anima_dir = Path.home() / ".animaworks" / "animas" / anima_name

    status_path = anima_dir / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    model = status.get("model", "codex/gpt-5.4")
    print(f"Model: {model}")

    from core.execution.codex_sdk import (
        CodexSDKExecutor,
        is_codex_sdk_available,
    )

    if not is_codex_sdk_available():
        print("ERROR: openai-codex-sdk not available")
        return

    print("Codex SDK available")

    from core.schemas import ModelConfig

    model_config = ModelConfig(model=model)

    executor = CodexSDKExecutor(
        model_config=model_config,
        anima_dir=anima_dir,
    )

    system_prompt = "You are a helpful assistant. Reply concisely in Japanese."
    executor._write_codex_config(system_prompt)
    codex = executor._create_codex_client()
    thread = codex.start_thread({
        "working_directory": str(anima_dir),
        "skip_git_repo_check": True,
    })

    print(f"Thread started. Sending: {message}")
    print(f"{'='*70}")
    print()

    streamed = await thread.run_streamed(message)

    t0 = time.monotonic()
    prev_t = t0
    event_count = 0

    async for event in streamed.events:
        now = time.monotonic()
        elapsed = now - t0
        gap = now - prev_t
        event_count += 1

        etype = getattr(event, "type", "?")
        item = getattr(event, "item", None)

        if item:
            item_type = getattr(item, "type", "?")
            item_id = getattr(item, "id", "?")
            text = ""
            if hasattr(item, "text"):
                text = item.text
            elif hasattr(item, "content"):
                text = str(item.content)

            text_preview = repr(text[:120]) if text else "(no text)"
            print(
                f"  [{elapsed:7.3f}s] +{gap*1000:7.1f}ms  "
                f"#{event_count:3d} {etype:20s}  "
                f"item_type={item_type:20s}  id={item_id}  "
                f"text_len={len(text):5d}  {text_preview}"
            )
        else:
            attrs = {}
            for attr in ("thread_id", "usage", "error", "message"):
                val = getattr(event, attr, None)
                if val is not None:
                    attrs[attr] = str(val)[:100]

            print(
                f"  [{elapsed:7.3f}s] +{gap*1000:7.1f}ms  "
                f"#{event_count:3d} {etype:20s}  {json.dumps(attrs, ensure_ascii=False)[:150]}"
            )

        prev_t = now

    total = time.monotonic() - t0
    print()
    print(f"{'='*70}")
    print(f"Total events: {event_count}")
    print(f"Elapsed: {total:.3f}s")


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "kaede"
    msg = sys.argv[2] if len(sys.argv) > 2 else "Hello, say hi in one sentence."
    asyncio.run(main(name, msg))
