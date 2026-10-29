from __future__ import annotations

"""Optional event-export port injected by the runtime infrastructure layer."""

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol


class ActivityEventExporter(Protocol):
    """Minimal interface required by activity logging."""

    def emit(self, payload: dict[str, Any]) -> None: ...


ActivityEventExporterFactory = Callable[[Path, Any | None], ActivityEventExporter | None]
_event_exporter_factory: ActivityEventExporterFactory | None = None


def set_activity_event_exporter_factory(factory: ActivityEventExporterFactory | None) -> None:
    """Inject or clear the infrastructure-owned event-exporter factory."""
    global _event_exporter_factory
    _event_exporter_factory = factory


def get_activity_event_exporter(
    anima_dir: Path,
    config: Any | None = None,
) -> ActivityEventExporter | None:
    """Return an exporter through the injected factory, if one is configured."""
    if _event_exporter_factory is None:
        return None
    return _event_exporter_factory(anima_dir, config)
