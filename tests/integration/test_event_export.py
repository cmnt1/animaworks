from __future__ import annotations

import json
import queue
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from core.config import invalidate_cache, save_config
from core.config.schemas import AnimaWorksConfig, EventExportConfig
from core.event_export import reset_event_exporters
from core.memory.activity import ActivityLogger
from core.memory.token_usage import TokenUsageLogger

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


class _ReusableHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class _Receiver:
    def __init__(self, port: int = 0) -> None:
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                receiver.events.put(payload)
                self.send_response(204)
                self.end_headers()

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self.server = _ReusableHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}/events"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


@pytest.fixture(autouse=True)
def _reset_exporter_lifecycle() -> Iterator[None]:
    reset_event_exporters()
    yield
    reset_event_exporters()


@pytest.fixture
def receiver() -> Iterator[_Receiver]:
    value = _Receiver()
    yield value
    value.close()


def _configure(data_dir: Path, url: str | None) -> None:
    save_config(
        AnimaWorksConfig(
            event_export=EventExportConfig(
                url=url,
                max_retries=0,
                backoff_base_seconds=0.01,
            )
        ),
        data_dir / "config.json",
    )
    invalidate_cache()


def _log_both(anima_dir: Path) -> None:
    ActivityLogger(anima_dir).log(
        "external_send",
        content="audit me",
        origin="human",
        ctx="chat",
    )
    TokenUsageLogger(anima_dir).log(
        model="claude-sonnet-4-6",
        trigger="chat",
        mode="a",
        input_tokens=100,
        output_tokens=25,
    )


def test_activity_and_token_usage_reach_loopback_receiver(
    data_dir: Path,
    receiver: _Receiver,
) -> None:
    _configure(data_dir, receiver.url)
    anima_dir = data_dir / "animas" / "alice"
    anima_dir.mkdir(parents=True)

    _log_both(anima_dir)

    events = [receiver.events.get(timeout=3), receiver.events.get(timeout=3)]
    by_kind = {event["kind"]: event for event in events}
    assert set(by_kind) == {"activity", "token_usage"}
    assert by_kind["activity"]["anima"] == "alice"
    assert by_kind["activity"]["event"]["type"] == "external_send"
    assert by_kind["activity"]["event"]["origin"] == "human"
    assert by_kind["token_usage"]["event"]["total_tokens"] == 125


def test_receiver_down_does_not_block_and_spool_recovers(data_dir: Path) -> None:
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    url = f"http://127.0.0.1:{port}/events"
    _configure(data_dir, url)
    anima_dir = data_dir / "animas" / "alice"
    anima_dir.mkdir(parents=True)

    started = time.monotonic()
    _log_both(anima_dir)
    elapsed = time.monotonic() - started

    assert elapsed < 1.0
    assert len(list((anima_dir / "state" / "event_export_spool").glob("*.jsonl"))) == 2

    receiver = _Receiver(port)
    try:
        events = [receiver.events.get(timeout=4), receiver.events.get(timeout=4)]
        assert {event["kind"] for event in events} == {"activity", "token_usage"}

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if not list((anima_dir / "state" / "event_export_spool").glob("*.jsonl")):
                break
            time.sleep(0.01)
        assert not list((anima_dir / "state" / "event_export_spool").glob("*.jsonl"))
    finally:
        receiver.close()


def test_persisted_spool_is_delivered_after_exporter_restart(data_dir: Path) -> None:
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    _configure(data_dir, f"http://127.0.0.1:{port}/events")
    anima_dir = data_dir / "animas" / "alice"
    anima_dir.mkdir(parents=True)

    ActivityLogger(anima_dir).log("external_send", content="survive restart")
    spool_dir = anima_dir / "state" / "event_export_spool"
    assert len(list(spool_dir.glob("*.jsonl"))) == 1
    reset_event_exporters()

    receiver = _Receiver(port)
    try:
        # Logger construction is the per-Anima process-start path.  No new
        # event is needed to wake delivery of the persisted spool entry.
        ActivityLogger(anima_dir)

        event = receiver.events.get(timeout=4)
        assert event["event"]["content"] == "survive restart"
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and list(spool_dir.glob("*.jsonl")):
            time.sleep(0.01)
        assert not list(spool_dir.glob("*.jsonl"))
    finally:
        receiver.close()


def test_worker_picks_up_endpoint_change_without_new_event(data_dir: Path) -> None:
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        unavailable_port = reserved.getsockname()[1]
    _configure(data_dir, f"http://127.0.0.1:{unavailable_port}/events")
    anima_dir = data_dir / "animas" / "alice"
    anima_dir.mkdir(parents=True)
    ActivityLogger(anima_dir).log("external_send", content="reload endpoint")
    assert list((anima_dir / "state" / "event_export_spool").glob("*.jsonl"))

    receiver = _Receiver()
    try:
        _configure(data_dir, receiver.url)

        event = receiver.events.get(timeout=4)
        assert event["event"]["content"] == "reload endpoint"
    finally:
        receiver.close()
