"""CLI access to phase3 vector stores through the active owner or server."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from core.memory.rag.owner_lock import VectorOwnerBusy, is_owner_lock_held
from core.memory.rag.store import VectorStore


@dataclass(frozen=True)
class ServerInfo:
    running: bool
    base_url: str


@dataclass
class VectorAccess:
    mode: Literal["server", "owner"]
    store: VectorStore
    _repair: Callable[[bool], dict[str, Any]]

    def repair(self, include_shared: bool) -> dict[str, Any]:
        """Rebuild the full phase3 database, including shared collections."""
        return self._repair(include_shared)


def detect_server() -> ServerInfo:
    """Detect the local server using its PID file and configured port."""
    from cli.commands.server import _is_process_alive, _read_pid

    pid = _read_pid()
    running = pid is not None and _is_process_alive(pid)
    try:
        from core.config import load_config

        port = load_config().server.port
    except Exception:
        port = 18500
    return ServerInfo(running=running, base_url=f"http://127.0.0.1:{port}/api")


def _configure_server_embeddings(server: ServerInfo) -> None:
    if not server.running:
        return
    os.environ.setdefault("ANIMAWORKS_EMBED_URL", f"{server.base_url}/internal/embed")
    os.environ.setdefault("ANIMAWORKS_RERANK_URL", f"{server.base_url}/internal/rerank")


def _repair_timeout_seconds() -> float:
    from core.config import load_config

    return float(getattr(load_config().rag, "repair_timeout_seconds", 1800)) + 60.0


def request_repair_and_wait(
    anima_name: str,
    *,
    include_shared: bool,
    reason: str,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Request a server-owned rebuild and wait for its persisted result."""
    from core.memory.rag import repair_state

    if timeout_seconds is None:
        timeout_seconds = _repair_timeout_seconds()
    current = repair_state.read_state(anima_name)
    if current.get("status") not in repair_state.ACTIVE_REPAIR_STATUSES:
        repair_state.write_repair_request_state(
            anima_name,
            reason=reason,
            collection=None,
            source="cli",
            include_shared=include_shared,
        )

    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        state = repair_state.read_state(anima_name)
        status = str(state.get("status", ""))
        if status in {"healthy", "success"}:
            return {"ok": True, **state}
        if (
            status in {"failed", "timeout", "repair_success_restart_failed"}
            or status.startswith("failed_")
            or status.startswith("blocked")
        ):
            return {"ok": False, **state}
        if time.monotonic() >= deadline:
            return {"ok": False, **state, "status": "timeout"}
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))


def _open_owner_access(
    anima_name: str,
    anima_dir: Path,
    *,
    purpose: str,
    wait_seconds: float,
) -> tuple[VectorAccess, Callable[[], None]]:
    from core.memory.rag.http_store import HttpVectorStore
    from core.memory.rag.owner_transport import owner_transport
    from core.supervisor.memory_service import MemoryService

    loop = asyncio.new_event_loop()
    ready = threading.Event()
    result: dict[str, Any] = {}
    service = MemoryService(anima_name, anima_dir, owner_label=f"cli:{purpose}")
    deadline = time.monotonic() + max(0.0, wait_seconds)

    async def start_service() -> None:
        while True:
            await service.start()
            if service._owner_lock.held:
                if service._store is None:
                    raise service._open_error or RuntimeError("MemoryService did not open its vector store")
                result["store"] = HttpVectorStore(
                    "",
                    anima_name,
                    transport=owner_transport(service.handle, loop),
                )
                return
            if time.monotonic() >= deadline:
                raise service._open_error or VectorOwnerBusy(f"Vector database owner is busy: {anima_name}")
            await asyncio.sleep(min(0.5, max(0.0, deadline - time.monotonic())))

    def run_loop() -> None:
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(start_service())
        except BaseException as exc:
            result["error"] = exc
        finally:
            ready.set()
        if "error" not in result:
            loop.run_forever()
        try:
            loop.run_until_complete(service.close())
        except Exception as exc:
            result.setdefault("close_error", exc)
        loop.close()

    thread = threading.Thread(target=run_loop, name=f"vector-owner-{anima_name}", daemon=True)
    thread.start()
    ready.wait()
    if "error" in result:
        thread.join()
        error = result["error"]
        if isinstance(error, VectorOwnerBusy):
            raise error
        raise RuntimeError(f"Could not start temporary vector owner for {anima_name}: {error}") from error

    access = VectorAccess(
        mode="owner",
        store=result["store"],
        _repair=lambda include_shared: asyncio.run_coroutine_threadsafe(
            service.repair(include_shared=True), loop
        ).result(),
    )

    def close() -> None:
        access.store.close()
        loop.call_soon_threadsafe(loop.stop)
        thread.join()

    return access, close


@contextmanager
def open_vector_access(
    anima_name: str,
    anima_dir: Path,
    *,
    purpose: str,
    wait_seconds: float = 30.0,
) -> Iterator[VectorAccess]:
    """Open a phase3 vector store through its server owner or a temporary owner."""
    server = detect_server()
    _configure_server_embeddings(server)

    if not is_owner_lock_held(anima_dir):
        access, close = _open_owner_access(
            anima_name,
            anima_dir,
            purpose=purpose,
            wait_seconds=wait_seconds,
        )
        try:
            yield access
        finally:
            close()
        return

    if server.running:
        from core.memory.rag.http_store import HttpVectorStore

        access = VectorAccess(
            mode="server",
            store=HttpVectorStore(f"{server.base_url}/internal/vector", anima_name),
            _repair=lambda include_shared: request_repair_and_wait(
                anima_name,
                include_shared=True,
                reason=f"cli_{purpose}",
                timeout_seconds=_repair_timeout_seconds(),
            ),
        )
        try:
            yield access
        finally:
            access.store.close()
        return

    from core.i18n import t

    raise VectorOwnerBusy(t("rag.cli_root_busy", anima=anima_name))
