"""ExternalMessagingChannelConfig.resolve_anima: explicit "" opts a channel out."""

from __future__ import annotations

from core.config.schemas import ExternalMessagingChannelConfig


def _cfg() -> ExternalMessagingChannelConfig:
    return ExternalMessagingChannelConfig(
        enabled=True,
        anima_mapping={"C_MAPPED": "sumire", "C_IGNORED": ""},
        default_anima="kotoha",
    )


def test_mapped_channel_returns_mapped_anima():
    assert _cfg().resolve_anima("C_MAPPED") == "sumire"


def test_unmapped_channel_falls_back_to_default():
    assert _cfg().resolve_anima("C_UNKNOWN") == "kotoha"
    assert _cfg().resolve_anima("D_DM") == "kotoha"


def test_empty_mapping_ignores_channel_instead_of_default():
    assert _cfg().resolve_anima("C_IGNORED") == ""


def test_no_default_and_unmapped_returns_empty():
    cfg = ExternalMessagingChannelConfig(anima_mapping={"C_IGNORED": ""})
    assert cfg.resolve_anima("C_IGNORED") == ""
    assert cfg.resolve_anima("C_OTHER") == ""
