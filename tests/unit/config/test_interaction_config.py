# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for :class:`InteractionConfig` and its place in the main config schema."""

from __future__ import annotations

from core.config.schemas import AnimaWorksConfig, InteractionConfig


class TestInteractionConfig:
    """InteractionConfig defaults and validators."""

    def test_defaults(self):
        cfg = InteractionConfig()
        assert cfg.ttl_days == 7
        assert cfg.web_base_url == ""
        assert cfg.default_approver_ids == []

    def test_coerce_default_approver_ids_from_legacy_dict(self):
        cfg = InteractionConfig(
            default_approver_ids={"slack": ["U1", "U2"], "discord": ["D9"]},
        )
        assert "U1" in cfg.default_approver_ids
        assert "U2" in cfg.default_approver_ids
        assert "D9" in cfg.default_approver_ids

    def test_anima_works_config_has_interaction(self):
        root = AnimaWorksConfig()
        assert isinstance(root.interaction, InteractionConfig)
        root.interaction = InteractionConfig(web_base_url="https://example.com", ttl_days=14)
        assert root.interaction.web_base_url == "https://example.com"
        assert root.interaction.ttl_days == 14
