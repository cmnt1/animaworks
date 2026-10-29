"""Cross-process wake fan-out for the PendingTaskExecutor.

Task submission can happen in two places:

* in the anima root process (tooling lanes call ``submit_tasks`` directly), or
* in a task-runner child process (``Mode S`` Claude Agent SDK hooks).

The ``PendingTaskExecutor`` that polls pending tasks lives only in the anima
root process.  To avoid always paying the 3-second poll interval after a
submission, this module registers a per-anima wake callback and fans a
``request_wake`` out to it:

* in-process, ``request_wake`` calls the callback directly; and
* from a child process, the child routes the request back to the root over
  IPC (``tasks_submitted`` event), where the root calls ``request_wake``.

The registry is process-local and protected by a lock so it is safe to call
from any thread (e.g. SDK hook threads).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_wake_handlers: dict[str, Callable[[], None]] = {}


def register_wake(anima_name: str, fn: Callable[[], None]) -> None:
    """Register the wake callback for ``anima_name``.

    Calling :func:`request_wake` for a registered name invokes ``fn``.
    Registering twice replaces the previous callback.
    """
    with _lock:
        _wake_handlers[anima_name] = fn


def unregister_wake(anima_name: str, fn: Callable[[], None] | None = None) -> None:
    """Remove the wake callback for ``anima_name``.

    If ``fn`` is given, only remove it when it is the currently registered
    callback (protects against a stale registration replacing a newer one).
    """
    with _lock:
        if fn is None or _wake_handlers.get(anima_name) is fn:
            _wake_handlers.pop(anima_name, None)


def request_wake(anima_name: str) -> bool:
    """Invoke the registered wake callback for ``anima_name``.

    Returns ``True`` when a callback was registered and invoked, ``False``
    when none is registered (the caller relies on polling instead).  A
    callback exception is swallowed (logged at debug level) so a failing
    wake never breaks task submission.
    """
    with _lock:
        fn = _wake_handlers.get(anima_name)
    if fn is None:
        return False
    try:
        fn()
    except Exception:
        logger.debug("wake callback failed for %s", anima_name, exc_info=True)
    return True
