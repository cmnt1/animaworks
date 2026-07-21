from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Best-effort webhook export for runtime activity and token usage events.

Producers only append payloads to a local per-Anima spool.  A single daemon
thread per Anima drains that spool in the background, so network failures can
never block the runtime path that produced an event.
"""

import fcntl
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.config.schemas import EventExportConfig

logger = logging.getLogger("animaworks.event_export")

_HTTP_TIMEOUT_SECONDS = 5.0
_IDLE_POLL_SECONDS = 1.0


class EventExporter:
    """Durable local spool and background webhook delivery for one Anima."""

    def __init__(
        self,
        anima_dir: Path,
        config: EventExportConfig,
        *,
        reload_config: bool = False,
    ) -> None:
        self.anima_dir = Path(anima_dir)
        self.spool_dir = self.anima_dir / "state" / "event_export_spool"
        self._config = config.model_copy(deep=True)
        self._reload_config = reload_config
        self._config_lock = threading.Lock()
        self._worker_state_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker_lock_file: Any | None = None

        # ``None`` is deliberately the only disabled value.  In particular,
        # an empty string is treated as an enabled (albeit invalid) endpoint.
        if config.url is None:
            return

        try:
            self.spool_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.warning(
                "Failed to create event export spool for %s",
                self.anima_dir.name,
                exc_info=True,
            )
            return

        self._ensure_worker()

    @property
    def worker_alive(self) -> bool:
        """Whether the background delivery worker is currently running."""
        return self._thread is not None and self._thread.is_alive()

    def update_config(self, config: EventExportConfig) -> None:
        """Apply a reloaded configuration while preserving worker identity."""
        with self._config_lock:
            self._config = config.model_copy(deep=True)
        self._wake_event.set()
        if config.url is not None:
            self._ensure_worker()

    def emit(self, payload: dict[str, Any]) -> None:
        """Append *payload* to the local spool and return without network I/O."""
        with self._config_lock:
            enabled = self._config.url is not None
        if not enabled or not self.spool_dir.is_dir():
            return

        tmp_path: Path | None = None
        try:
            line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
            name = f"{time.time_ns():020d}-{uuid4().hex}.jsonl"
            path = self.spool_dir / name
            tmp_path = path.with_suffix(".tmp")
            tmp_path.write_text(line, encoding="utf-8")
            os.replace(tmp_path, path)
            self._wake_event.set()
        except Exception:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            # Export is observability only and must never affect the caller.
            logger.warning(
                "Failed to append event export spool for %s",
                self.anima_dir.name,
                exc_info=True,
            )

    def stop(self, timeout: float = 1.0) -> None:
        """Request worker shutdown (primarily for config reload and tests)."""
        self._stop_event.set()
        self._wake_event.set()
        if self._thread is not None and timeout > 0:
            self._thread.join(timeout=timeout)

    def _ensure_worker(self) -> None:
        """Start the sole cross-process delivery worker for this Anima."""
        if self._stop_event.is_set() or not self.spool_dir.is_dir():
            return
        with self._worker_state_lock:
            if self._thread is not None and self._thread.is_alive():
                return

            lock_file = (self.spool_dir / ".worker.lock").open("a+")
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock_file.close()
                return

            self._worker_lock_file = lock_file
            self._thread = threading.Thread(
                target=self._run,
                name=f"event-export-{self.anima_dir.name}",
                daemon=True,
            )
            try:
                self._thread.start()
            except Exception:
                self._release_worker_lock_locked()
                self._thread = None
                raise

    def _release_worker_lock_locked(self) -> None:
        if self._worker_lock_file is None:
            return
        try:
            fcntl.flock(self._worker_lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            self._worker_lock_file.close()
            self._worker_lock_file = None

    def _config_snapshot(self) -> EventExportConfig:
        with self._config_lock:
            return self._config.model_copy(deep=True)

    def _refresh_config_from_disk(self) -> None:
        """Refresh shared config so the cross-process worker sees reloads."""
        if not self._reload_config:
            return
        try:
            from core.config import load_config

            config = load_config().event_export
        except Exception:
            logger.warning("Failed to reload event export configuration", exc_info=True)
            return
        with self._config_lock:
            self._config = config.model_copy(deep=True)

    def _spool_files(self) -> list[Path]:
        try:
            return sorted(self.spool_dir.glob("*.jsonl"), key=lambda path: path.name)
        except OSError:
            logger.warning(
                "Failed to list event export spool for %s",
                self.anima_dir.name,
                exc_info=True,
            )
            return []

    def _enforce_spool_limit(self, files: list[Path]) -> list[Path]:
        config = self._config_snapshot()
        max_bytes = config.spool_max_mb * 1024 * 1024
        sizes: dict[Path, int] = {}
        total = 0
        for path in files:
            try:
                size = path.stat().st_size
            except OSError:
                continue
            sizes[path] = size
            total += size

        removed = 0
        removed_bytes = 0
        removed_paths: set[Path] = set()
        for path in files:
            if total <= max_bytes:
                break
            size = sizes.get(path, 0)
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError:
                logger.warning("Failed to trim event export spool file %s", path, exc_info=True)
                continue
            total -= size
            removed += 1
            removed_bytes += size
            removed_paths.add(path)

        if removed:
            logger.warning(
                "Event export spool for %s exceeded %d MiB; discarded %d oldest "
                "event(s) (%d bytes)",
                self.anima_dir.name,
                config.spool_max_mb,
                removed,
                removed_bytes,
            )
        return [path for path in files if path not in removed_paths]

    def _cleanup_stale_temp_files(self) -> None:
        """Remove abandoned atomic-write files without racing active emitters."""
        cutoff = time.time() - 60
        try:
            temp_files = list(self.spool_dir.glob("*.tmp"))
        except OSError:
            return
        for path in temp_files:
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except FileNotFoundError:
                continue
            except OSError:
                logger.warning("Failed to clean stale event export temp file %s", path, exc_info=True)

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                self._wake_event.clear()
                try:
                    self._refresh_config_from_disk()
                    config = self._config_snapshot()
                    if config.url is None:
                        self._wake_event.wait(_IDLE_POLL_SECONDS)
                        continue
                    self._cleanup_stale_temp_files()
                    files = self._spool_files()
                    files = self._enforce_spool_limit(files)
                    if not files:
                        self._wake_event.wait(_IDLE_POLL_SECONDS)
                        continue

                    for path in files:
                        if self._stop_event.is_set():
                            break
                        delivered = self._deliver(path)
                        if not delivered:
                            config = self._config_snapshot()
                            self._stop_event.wait(max(config.backoff_base_seconds, 0.05))
                            break
                except Exception:
                    logger.warning(
                        "Unexpected event export worker failure for %s",
                        self.anima_dir.name,
                        exc_info=True,
                    )
                    self._stop_event.wait(_IDLE_POLL_SECONDS)
        finally:
            with self._worker_state_lock:
                self._release_worker_lock_locked()

    def _deliver(self, path: Path) -> bool:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return True
        except (OSError, json.JSONDecodeError):
            logger.warning("Failed to read event export spool file %s", path, exc_info=True)
            return False

        config = self._config_snapshot()
        if config.url is None:
            return False

        # ``requests`` is optional for installations that do not enable event
        # export, so import it only inside the enabled background worker.
        try:
            import requests
        except ImportError:
            logger.warning("Event export requires the communication extra (requests)")
            return False

        attempts = max(1, config.max_retries + 1)
        last_error: str = ""
        for attempt in range(attempts):
            if self._stop_event.is_set():
                return False
            self._refresh_config_from_disk()
            config = self._config_snapshot()
            if config.url is None:
                return False
            response = None
            try:
                response = requests.post(
                    config.url,
                    json=payload,
                    headers=config.headers,
                    timeout=_HTTP_TIMEOUT_SECONDS,
                    allow_redirects=False,
                )
                if 200 <= response.status_code < 300:
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                    return True
                last_error = f"HTTP {response.status_code}"
            except requests.RequestException as exc:
                last_error = str(exc)
            finally:
                if response is not None:
                    response.close()

            if attempt < attempts - 1:
                delay = config.backoff_base_seconds * (2**attempt)
                if self._stop_event.wait(delay):
                    return False

        logger.warning(
            "Event export delivery failed for %s after %d attempt(s); keeping %s in spool: %s",
            self.anima_dir.name,
            attempts,
            path.name,
            last_error,
        )
        return False


_exporters: dict[Path, EventExporter] = {}
_exporters_lock = threading.Lock()


def get_event_exporter(
    anima_dir: Path,
    config: EventExportConfig | None = None,
) -> EventExporter | None:
    """Return the process-wide exporter for *anima_dir*, if configured."""
    if config is None:
        from core.config import load_config

        config = load_config().event_export

    key = Path(anima_dir).resolve()
    with _exporters_lock:
        existing = _exporters.get(key)
        if config.url is None:
            if existing is not None:
                existing.update_config(config)
            exporter = None
        elif existing is not None:
            existing.update_config(config)
            exporter = existing
        else:
            exporter = EventExporter(key, config, reload_config=True)
            if exporter.spool_dir.is_dir():
                _exporters[key] = exporter

    return exporter


def reset_event_exporters() -> None:
    """Stop and clear all exporters; intended for isolated test lifecycles."""
    with _exporters_lock:
        exporters = list(_exporters.values())
        _exporters.clear()
    for exporter in exporters:
        exporter.stop(timeout=2.0)


__all__ = ["EventExporter", "get_event_exporter", "reset_event_exporters"]
