#!/usr/bin/env python3
"""Debug IPC streaming: send message to an anima and log every SSE event with timing."""
from __future__ import annotations

import argparse
import json
import sys
import time

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug SSE streaming timing")
    parser.add_argument("anima", help="Anima name")
    parser.add_argument("--message", "-m", default="こんにちは、簡単に自己紹介してください。",
                        help="Message to send")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}/api/animas/{args.anima}/chat/stream"
    payload = {
        "message": args.message,
        "from_person": "debug_user",
        "thread_id": "debug_stream_test",
    }

    print(f"=== SSE Stream Debug: {args.anima} ===")
    print(f"URL: {url}")
    print(f"Message: {args.message}")
    print(f"{'='*60}")
    print()

    t0 = time.monotonic()
    prev_t = t0
    event_count = 0
    text_delta_count = 0
    total_text_len = 0
    first_text_t = None

    with httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
        with client.stream("POST", url, json=payload) as resp:
            if resp.status_code != 200:
                print(f"ERROR: HTTP {resp.status_code}")
                print(resp.read().decode())
                return

            event_name = ""
            data_buf = ""

            for raw_line in resp.iter_lines():
                now = time.monotonic()
                elapsed = now - t0
                gap = now - prev_t

                if raw_line.startswith("event: "):
                    event_name = raw_line[7:]
                    continue
                elif raw_line.startswith("data: "):
                    data_buf = raw_line[6:]
                elif raw_line.startswith("id: "):
                    continue
                elif raw_line.startswith(":"):
                    print(f"  [{elapsed:7.3f}s] (keepalive comment)")
                    prev_t = now
                    continue
                elif raw_line == "":
                    if not event_name and not data_buf:
                        continue
                    event_count += 1

                    try:
                        payload_data = json.loads(data_buf) if data_buf else {}
                    except json.JSONDecodeError:
                        payload_data = {"raw": data_buf}

                    if event_name == "text_delta":
                        text = payload_data.get("text", "")
                        text_delta_count += 1
                        total_text_len += len(text)
                        if first_text_t is None:
                            first_text_t = elapsed
                        text_preview = repr(text[:80])
                        print(
                            f"  [{elapsed:7.3f}s] +{gap*1000:7.1f}ms "
                            f"#{event_count:4d} text_delta  len={len(text):4d}  "
                            f"total={total_text_len:6d}  {text_preview}"
                        )
                    elif event_name == "done":
                        summary = payload_data.get("summary", "")[:80]
                        print(
                            f"  [{elapsed:7.3f}s] +{gap*1000:7.1f}ms "
                            f"#{event_count:4d} done  summary_len={len(payload_data.get('summary',''))}"
                        )
                    elif event_name in ("thinking_delta", "thinking_start", "thinking_end"):
                        text = payload_data.get("text", "")
                        print(
                            f"  [{elapsed:7.3f}s] +{gap*1000:7.1f}ms "
                            f"#{event_count:4d} {event_name}  len={len(text)}"
                        )
                    else:
                        detail = json.dumps(payload_data, ensure_ascii=False)[:120]
                        print(
                            f"  [{elapsed:7.3f}s] +{gap*1000:7.1f}ms "
                            f"#{event_count:4d} {event_name}  {detail}"
                        )

                    prev_t = now
                    event_name = ""
                    data_buf = ""
                    continue

    total_elapsed = time.monotonic() - t0
    print()
    print(f"{'='*60}")
    print(f"=== Summary ===")
    print(f"  Total events:      {event_count}")
    print(f"  text_delta events: {text_delta_count}")
    print(f"  Total text length: {total_text_len}")
    print(f"  Total elapsed:     {total_elapsed:.3f}s")
    if first_text_t is not None:
        print(f"  Time to first text: {first_text_t:.3f}s")
    if text_delta_count > 1:
        avg_gap = (total_elapsed - (first_text_t or 0)) / text_delta_count
        print(f"  Avg gap between text_deltas: {avg_gap*1000:.1f}ms")


if __name__ == "__main__":
    main()
