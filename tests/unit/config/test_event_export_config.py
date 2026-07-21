from __future__ import annotations

from core.config.schemas import AnimaWorksConfig, EventExportConfig


def test_event_export_defaults_are_opt_in() -> None:
    config = AnimaWorksConfig()

    assert config.event_export == EventExportConfig()
    assert config.event_export.url is None
    assert config.event_export.headers == {}
    assert config.event_export.event_types is None
    assert config.event_export.include_token_usage is True
    assert config.event_export.max_retries == 8
    assert config.event_export.backoff_base_seconds == 2.0
    assert config.event_export.spool_max_mb == 64


def test_event_export_configuration_round_trip() -> None:
    raw = {
        "event_export": {
            "url": "https://audit.example.invalid/events",
            "headers": {"Authorization": "Bearer token"},
            "event_types": ["external_send"],
            "include_token_usage": False,
            "max_retries": 3,
            "backoff_base_seconds": 0.25,
            "spool_max_mb": 12,
        }
    }

    config = AnimaWorksConfig.model_validate(raw)
    dumped = config.model_dump(mode="json")["event_export"]

    assert dumped == raw["event_export"]


def test_event_export_headers_are_not_shared_between_configs() -> None:
    first = EventExportConfig()
    second = EventExportConfig()

    first.headers["X-Test"] = "one"

    assert second.headers == {}
