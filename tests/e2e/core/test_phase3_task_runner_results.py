"""Phase 3 task runners return terminal results after root memory RPCs."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from core.runtime import ipc_v2
from core.runtime.memory_service import MemoryService
from core.runtime.task_runner_supervisor import TaskRunnerSupervisor
from core.schemas import CronTask


class _MockEngineHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        if "embed" in self.path:
            body = {"embeddings": [[1.0, 0.0, 0.0] for _ in payload.get("texts", [])]}
            encoded = json.dumps(body).encode()
            content_type = "application/json"
        elif payload.get("stream"):
            # process_message uses the streaming execution path after 18b30d5c.
            chunks = [
                {
                    "id": "mock-chat",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "mock",
                    "choices": [
                        {"index": 0, "delta": {"role": "assistant", "content": "mock reply"}, "finish_reason": None}
                    ],
                },
                {
                    "id": "mock-chat",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "mock",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                },
                {
                    "id": "mock-chat",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "mock",
                    "choices": [],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            ]
            encoded = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks).encode() + b"data: [DONE]\n\n"
            content_type = "text/event-stream"
        else:
            body = {
                "id": "mock-chat",
                "object": "chat.completion",
                "created": 0,
                "model": "mock",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "mock reply"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
            encoded = json.dumps(body).encode()
            content_type = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *args: object) -> None:
        pass


@pytest.fixture
def mock_engine_url() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockEngineHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.mark.asyncio
@pytest.mark.parametrize("lane", ["cron", "chat"])
async def test_phase3_returns_cron_command_and_chat_results(
    lane: str,
    data_dir: Path,
    make_anima: Callable[..., Path],
    mock_engine_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir = make_anima(
        "phase3-result",
        model="openai/mock",
        execution_mode="assisted",
        credential="openai",
        api_key="test",
        api_base_url=f"{mock_engine_url}/v1",
    )
    status_path = anima_dir / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["process_model"] = "phase3"
    status_path.write_text(json.dumps(status), encoding="utf-8")
    monkeypatch.setenv("ANIMAWORKS_EMBED_URL", f"{mock_engine_url}/embed")
    # Task runners require explicit vector and rerank URLs after the service split (a2f29ea0).
    monkeypatch.setenv("ANIMAWORKS_VECTOR_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("ANIMAWORKS_RERANK_URL", "http://127.0.0.1:9")

    read_envelope = ipc_v2.read_ipc_v2_envelope

    async def delayed_terminal_response(reader: asyncio.StreamReader) -> ipc_v2.IPCV2Envelope:
        envelope = await read_envelope(reader)
        if envelope.kind == "response" and envelope.body["request_id"].startswith("run-"):
            await asyncio.sleep(0.5)
        return envelope

    monkeypatch.setattr(ipc_v2, "read_ipc_v2_envelope", delayed_terminal_response)

    supervisor = TaskRunnerSupervisor(
        "phase3-result",
        anima_dir,
        data_dir / "shared",
        memory_service=MemoryService("phase3-result", anima_dir),
    )
    try:
        if lane == "cron":
            result = await supervisor.run_cron(
                CronTask(
                    name="phase3-command",
                    schedule="0 0 1 1 *",
                    type="command",
                    command="printf command-result",
                    trigger_heartbeat=False,
                )
            )
            assert result["result"]["stdout"] == "command-result"
        else:
            result = await supervisor.run_chat(
                kind="message",
                payload={"message": "hello", "from_person": "human", "thread_id": "default"},
            )
            assert result["response"] == "mock reply"
        assert (data_dir / "logs" / "animas" / "phase3-result" / "task-runner.stderr.log").is_file()
    finally:
        await supervisor.close()
