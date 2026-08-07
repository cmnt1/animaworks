"""Persistent duplex IPC v2 used between an anima root and task runners."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Literal

IPC_V2_VERSION = 2
IPC_V2_MAX_FRAME_BYTES = 4 * 1024 * 1024
IPC_V2_WINDOW_MAX_FRAMES = 64
IPC_V2_WINDOW_MAX_BYTES = 4 * 1024 * 1024
IPC_V2_QUEUE_MAX_FRAMES = 256
IPC_V2_QUEUE_MAX_BYTES = 16 * 1024 * 1024
IPC_V2_CONTROL_MAX_FRAMES = 8
IPC_V2_CONTROL_MAX_BYTES = 512 * 1024
IPC_V2_BACKPRESSURE_TIMEOUT = 5.0
IPC_V2_HEARTBEAT_INTERVAL = 5.0
IPC_V2_HALF_OPEN_TIMEOUT = 15.0

IPC_KIND = Literal["request", "response", "event"]
IPC_LANES = frozenset({"chat", "heartbeat", "cron", "task", "background"})

_BASE_FIELDS = {
    "v",
    "kind",
    "job_id",
    "seq",
    "root_epoch",
    "attempt",
    "lane",
    "display_lane",
}
_KIND_FIELDS = {
    "request": {"request_id", "method", "params"},
    "response": {"request_id", "result", "error"},
    "event": {"event", "data"},
}


class IPCV2Error(Exception):
    """Base IPC v2 error."""

    code = "PROTOCOL_ERROR"


class IPCV2ProtocolError(IPCV2Error):
    """A frame violates the wire contract."""


class IPCV2PayloadTooLarge(IPCV2Error):
    """A frame exceeds the 4 MiB wire limit."""

    code = "PAYLOAD_TOO_LARGE"


class IPCV2ConnectionError(IPCV2Error):
    """The persistent connection was closed or became unusable."""

    code = "UNAVAILABLE"


class IPCV2BackpressureTimeout(IPCV2Error):
    """The peer did not advance its ACK window in time."""

    code = "BACKPRESSURE_TIMEOUT"


@dataclass(frozen=True)
class IPCV2Identity:
    """Fields that identify one job attempt."""

    job_id: str
    root_epoch: str
    attempt: int
    lane: str
    display_lane: str

    def validate(self) -> None:
        if not isinstance(self.job_id, str) or not self.job_id:
            raise IPCV2ProtocolError("job_id must be a non-empty string")
        if not isinstance(self.root_epoch, str):
            raise IPCV2ProtocolError("root_epoch must be a UUID string")
        try:
            uuid.UUID(self.root_epoch)
        except (ValueError, TypeError, AttributeError) as exc:
            raise IPCV2ProtocolError("root_epoch must be a UUID string") from exc
        if not isinstance(self.attempt, int) or isinstance(self.attempt, bool) or self.attempt < 1:
            raise IPCV2ProtocolError("attempt must be an integer >= 1")
        if self.lane not in IPC_LANES:
            raise IPCV2ProtocolError(f"invalid lane: {self.lane!r}")
        if not isinstance(self.display_lane, str) or not self.display_lane:
            raise IPCV2ProtocolError("display_lane must be a non-empty string")


@dataclass(frozen=True)
class IPCV2Envelope:
    """Validated IPC v2 envelope."""

    kind: IPC_KIND
    identity: IPCV2Identity
    seq: int
    body: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "v": IPC_V2_VERSION,
            "kind": self.kind,
            "job_id": self.identity.job_id,
            "seq": self.seq,
            "root_epoch": self.identity.root_epoch,
            "attempt": self.identity.attempt,
            "lane": self.identity.lane,
            "display_lane": self.identity.display_lane,
            **self.body,
        }

    def to_bytes(self) -> bytes:
        payload = json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        if len(payload) > IPC_V2_MAX_FRAME_BYTES:
            raise IPCV2PayloadTooLarge(
                f"IPC v2 frame is {len(payload)} bytes; maximum is {IPC_V2_MAX_FRAME_BYTES}"
            )
        return payload + b"\n"

    @classmethod
    def from_bytes(cls, payload: bytes) -> IPCV2Envelope:
        raw = payload.rstrip(b"\r\n")
        if len(raw) > IPC_V2_MAX_FRAME_BYTES:
            raise IPCV2PayloadTooLarge(
                f"IPC v2 frame is {len(raw)} bytes; maximum is {IPC_V2_MAX_FRAME_BYTES}"
            )
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IPCV2ProtocolError(f"invalid JSON frame: {exc}") from exc
        if not isinstance(data, dict):
            raise IPCV2ProtocolError("frame must be a JSON object")
        if data.get("v") != IPC_V2_VERSION or isinstance(data.get("v"), bool):
            raise IPCV2ProtocolError("v must be integer 2")
        kind = data.get("kind")
        if kind not in _KIND_FIELDS:
            raise IPCV2ProtocolError(f"invalid kind: {kind!r}")
        allowed = _BASE_FIELDS | _KIND_FIELDS[kind]
        unknown = set(data) - allowed
        if unknown:
            raise IPCV2ProtocolError(f"unknown field(s): {', '.join(sorted(unknown))}")
        missing = _BASE_FIELDS - set(data)
        if missing:
            raise IPCV2ProtocolError(f"missing field(s): {', '.join(sorted(missing))}")

        identity = IPCV2Identity(
            job_id=data["job_id"],
            root_epoch=data["root_epoch"],
            attempt=data["attempt"],
            lane=data["lane"],
            display_lane=data["display_lane"],
        )
        identity.validate()
        seq = data["seq"]
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
            raise IPCV2ProtocolError("seq must be an integer >= 1")
        body = {key: value for key, value in data.items() if key not in _BASE_FIELDS}
        cls._validate_body(kind, body)
        return cls(kind=kind, identity=identity, seq=seq, body=body)

    @staticmethod
    def _validate_body(kind: str, body: dict[str, Any]) -> None:
        if kind == "request":
            if not isinstance(body.get("request_id"), str) or not body["request_id"]:
                raise IPCV2ProtocolError("request requires request_id")
            if not isinstance(body.get("method"), str) or not body["method"]:
                raise IPCV2ProtocolError("request requires method")
            if not isinstance(body.get("params", {}), dict):
                raise IPCV2ProtocolError("request params must be an object")
        elif kind == "response":
            if not isinstance(body.get("request_id"), str) or not body["request_id"]:
                raise IPCV2ProtocolError("response requires request_id")
            has_result = "result" in body and body["result"] is not None
            has_error = "error" in body and body["error"] is not None
            if has_result == has_error:
                raise IPCV2ProtocolError("response must contain exactly one of result or error")
            if has_error:
                error = body["error"]
                if not isinstance(error, dict):
                    raise IPCV2ProtocolError("response error must be an object")
                if not isinstance(error.get("code"), str) or not isinstance(error.get("message"), str):
                    raise IPCV2ProtocolError("response error requires code and message")
                if not isinstance(error.get("retryable"), bool):
                    raise IPCV2ProtocolError("response error requires boolean retryable")
        else:
            if not isinstance(body.get("event"), str) or not body["event"]:
                raise IPCV2ProtocolError("event requires event name")
            if not isinstance(body.get("data", {}), dict):
                raise IPCV2ProtocolError("event data must be an object")


@dataclass
class IPCV2ConnectionState:
    """Replay and sequence state retained across reconnects."""

    identity: IPCV2Identity
    send_seq: int = 0
    received_seq: int = 0
    last_acked_seq: int = 0
    unacked: OrderedDict[int, bytes] = field(default_factory=OrderedDict)
    unacked_bytes: int = 0


class IPCV2Connection:
    """One persistent duplex connection with cumulative ACK and replay state."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        state: IPCV2ConnectionState,
    ) -> None:
        state.identity.validate()
        self.reader = reader
        self.writer = writer
        self.state = state
        self.last_traffic_at = time.monotonic()
        self._send_lock = asyncio.Lock()
        self._window_changed = asyncio.Condition()
        self._closed = False

    async def send_request(self, request_id: str, method: str, params: dict[str, Any]) -> int:
        return await self._send("request", {"request_id": request_id, "method": method, "params": params})

    async def send_response(
        self,
        request_id: str,
        *,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> int:
        body: dict[str, Any] = {"request_id": request_id}
        if error is not None:
            body["error"] = error
        else:
            body["result"] = result
        return await self._send("response", body)

    async def send_event(self, event: str, data: dict[str, Any] | None = None) -> int:
        return await self._send("event", {"event": event, "data": data or {}})

    async def _send(self, kind: IPC_KIND, body: dict[str, Any]) -> int:
        is_ack = kind == "event" and body.get("event") == "ack"
        while True:
            frame_bytes = 0
            async with self._send_lock:
                if self._closed:
                    raise IPCV2ConnectionError("connection is closed")
                next_seq = self.state.send_seq + 1
                envelope = IPCV2Envelope(kind=kind, identity=self.state.identity, seq=next_seq, body=body)
                wire = envelope.to_bytes()
                frame_bytes = len(wire) - 1
                if is_ack or self._window_available(frame_bytes):
                    self.writer.write(wire)
                    try:
                        await asyncio.wait_for(self.writer.drain(), timeout=IPC_V2_BACKPRESSURE_TIMEOUT)
                    except (TimeoutError, ConnectionError, OSError) as exc:
                        self._closed = True
                        if isinstance(exc, TimeoutError):
                            raise IPCV2BackpressureTimeout(
                                "writer.drain() did not advance for 5 seconds"
                            ) from exc
                        raise IPCV2ConnectionError(f"write failed: {exc}") from exc
                    self.state.send_seq = next_seq
                    self.last_traffic_at = time.monotonic()
                    if not is_ack:
                        self.state.unacked[next_seq] = wire
                        self.state.unacked_bytes += frame_bytes
                    return next_seq
            await self._wait_for_window(frame_bytes)

    def _window_available(self, frame_bytes: int) -> bool:
        return (
            len(self.state.unacked) < IPC_V2_WINDOW_MAX_FRAMES
            and self.state.unacked_bytes + frame_bytes <= IPC_V2_WINDOW_MAX_BYTES
        )

    async def _wait_for_window(self, frame_bytes: int) -> None:
        def available() -> bool:
            return self._window_available(frame_bytes)

        if available():
            return
        try:
            async with self._window_changed:
                await asyncio.wait_for(self._window_changed.wait_for(available), IPC_V2_BACKPRESSURE_TIMEOUT)
        except TimeoutError as exc:
            raise IPCV2BackpressureTimeout("ACK window did not advance for 5 seconds") from exc

    async def receive(self) -> IPCV2Envelope:
        """Receive and ACK the next non-ACK, non-duplicate frame."""
        while True:
            envelope = await read_ipc_v2_envelope(self.reader)
            if envelope.identity != self.state.identity:
                raise IPCV2ProtocolError("job identity changed within a connection")
            self.last_traffic_at = time.monotonic()
            duplicate = envelope.seq <= self.state.received_seq
            self.state.received_seq = max(self.state.received_seq, envelope.seq)
            if envelope.kind == "event" and envelope.body["event"] == "ack":
                await self._apply_ack(envelope.body["data"].get("ack_seq"))
                continue
            await self._send_ack(envelope.seq)
            if duplicate:
                continue
            return envelope

    async def accept_first(self, envelope: IPCV2Envelope) -> IPCV2Envelope | None:
        """Attach a frame read before the job-specific state was known."""
        if envelope.identity != self.state.identity:
            raise IPCV2ProtocolError("job identity does not match registry")
        duplicate = envelope.seq <= self.state.received_seq
        self.state.received_seq = max(self.state.received_seq, envelope.seq)
        self.last_traffic_at = time.monotonic()
        if envelope.kind == "event" and envelope.body["event"] == "ack":
            await self._apply_ack(envelope.body["data"].get("ack_seq"))
            return None
        await self._send_ack(envelope.seq)
        return None if duplicate else envelope

    async def _send_ack(self, seq: int) -> None:
        await self._send("event", {"event": "ack", "data": {"ack_seq": seq}})

    async def _apply_ack(self, ack_seq: Any) -> None:
        if not isinstance(ack_seq, int) or isinstance(ack_seq, bool) or ack_seq < 0:
            raise IPCV2ProtocolError("ack_seq must be a non-negative integer")
        if ack_seq > self.state.send_seq:
            raise IPCV2ProtocolError("ack_seq exceeds the last sent sequence")
        removed = False
        for seq in list(self.state.unacked):
            if seq > ack_seq:
                break
            wire = self.state.unacked.pop(seq)
            self.state.unacked_bytes -= len(wire) - 1
            removed = True
        self.state.last_acked_seq = max(self.state.last_acked_seq, ack_seq)
        if removed:
            async with self._window_changed:
                self._window_changed.notify_all()

    async def replay_after(self, received_seq: int, *, through_seq: int | None = None) -> None:
        """Replay unacknowledged non-ACK frames after reconnect."""
        async with self._send_lock:
            for seq, wire in self.state.unacked.items():
                if seq <= received_seq:
                    continue
                if through_seq is not None and seq > through_seq:
                    continue
                self.writer.write(wire)
                await asyncio.wait_for(self.writer.drain(), timeout=IPC_V2_BACKPRESSURE_TIMEOUT)
            self.last_traffic_at = time.monotonic()

    def is_half_open(self, now: float | None = None) -> bool:
        return (now or time.monotonic()) - self.last_traffic_at >= IPC_V2_HALF_OPEN_TIMEOUT

    async def close(self) -> None:
        self._closed = True
        if not self.writer.is_closing():
            self.writer.close()
        try:
            await self.writer.wait_closed()
        except (ConnectionError, BrokenPipeError):
            pass


async def read_ipc_v2_envelope(reader: asyncio.StreamReader) -> IPCV2Envelope:
    """Read one bounded JSON Lines envelope and detect EOF explicitly."""
    try:
        payload = await reader.readline()
    except (ValueError, asyncio.LimitOverrunError) as exc:
        raise IPCV2PayloadTooLarge("IPC v2 frame exceeded the reader limit") from exc
    if not payload:
        raise IPCV2ConnectionError("peer disconnected")
    if len(payload.rstrip(b"\r\n")) > IPC_V2_MAX_FRAME_BYTES:
        raise IPCV2PayloadTooLarge("IPC v2 frame exceeded 4 MiB")
    return IPCV2Envelope.from_bytes(payload)


def ipc_v2_error(code: str, message: str, *, retryable: bool) -> dict[str, Any]:
    """Build the required compact error object."""
    return {"code": code, "message": message, "retryable": retryable}


__all__ = [
    "IPC_V2_HALF_OPEN_TIMEOUT",
    "IPC_V2_MAX_FRAME_BYTES",
    "IPCV2BackpressureTimeout",
    "IPCV2Connection",
    "IPCV2ConnectionError",
    "IPCV2ConnectionState",
    "IPCV2Envelope",
    "IPCV2Error",
    "IPCV2Identity",
    "IPCV2PayloadTooLarge",
    "IPCV2ProtocolError",
    "ipc_v2_error",
    "read_ipc_v2_envelope",
]
