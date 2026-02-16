"""Tests for background task config models in core/config/models.py."""
from __future__ import annotations

from core.config.models import (
    AnimaWorksConfig,
    BackgroundTaskConfig,
    BackgroundToolConfig,
    ServerConfig,
)


# ── ServerConfig ─────────────────────────────────────────────


class TestServerConfig:
    def test_server_config_defaults(self):
        """ServerConfig defaults to ipc_stream_timeout=60 and keepalive_interval=30."""
        sc = ServerConfig()
        assert sc.ipc_stream_timeout == 60
        assert sc.keepalive_interval == 30


# ── BackgroundTaskConfig ─────────────────────────────────────


class TestBackgroundTaskConfig:
    def test_background_task_config_defaults(self):
        """BackgroundTaskConfig has expected defaults."""
        btc = BackgroundTaskConfig()
        assert btc.enabled is True
        assert btc.result_retention_hours == 24
        assert isinstance(btc.eligible_tools, dict)

    def test_background_task_config_eligible_tools(self):
        """Eligible tools include image_generation, local_llm, run_command."""
        btc = BackgroundTaskConfig()
        assert "image_generation" in btc.eligible_tools
        assert "local_llm" in btc.eligible_tools
        assert "run_command" in btc.eligible_tools

        # Verify threshold values
        assert btc.eligible_tools["image_generation"].threshold_s == 30
        assert btc.eligible_tools["local_llm"].threshold_s == 60
        assert btc.eligible_tools["run_command"].threshold_s == 60

    def test_background_tool_config_defaults(self):
        """BackgroundToolConfig has a default threshold_s."""
        btool = BackgroundToolConfig()
        assert btool.threshold_s == 30

    def test_background_tool_config_custom(self):
        """BackgroundToolConfig accepts custom threshold."""
        btool = BackgroundToolConfig(threshold_s=120)
        assert btool.threshold_s == 120


# ── AnimaWorksConfig integration ─────────────────────────────


class TestAnimaWorksConfigBackground:
    def test_animaworks_config_has_server(self):
        """AnimaWorksConfig includes server field with correct type."""
        config = AnimaWorksConfig()
        assert isinstance(config.server, ServerConfig)
        assert config.server.ipc_stream_timeout == 60
        assert config.server.keepalive_interval == 30

    def test_animaworks_config_has_background_task(self):
        """AnimaWorksConfig includes background_task field with correct type."""
        config = AnimaWorksConfig()
        assert isinstance(config.background_task, BackgroundTaskConfig)
        assert config.background_task.enabled is True

    def test_config_serialization_roundtrip(self):
        """model_dump / model_validate round-trip works for background config."""
        config = AnimaWorksConfig()
        # Modify background_task settings
        config.background_task.enabled = False
        config.background_task.result_retention_hours = 48
        config.background_task.eligible_tools["custom_tool"] = BackgroundToolConfig(
            threshold_s=90,
        )
        config.server.ipc_stream_timeout = 600

        # Serialize and deserialize
        data = config.model_dump(mode="json")
        restored = AnimaWorksConfig.model_validate(data)

        # Verify background_task round-trip
        assert restored.background_task.enabled is False
        assert restored.background_task.result_retention_hours == 48
        assert "custom_tool" in restored.background_task.eligible_tools
        assert restored.background_task.eligible_tools["custom_tool"].threshold_s == 90

        # Verify server round-trip
        assert restored.server.ipc_stream_timeout == 600

        # Verify default eligible tools survived round-trip
        assert "image_generation" in restored.background_task.eligible_tools
        assert restored.background_task.eligible_tools["image_generation"].threshold_s == 30
