from __future__ import annotations

from core.provider_cooldown import (
    clear_provider_cooldown,
    format_cooldown_message,
    get_provider_cooldown,
    provider_key_for_model_config,
    record_provider_rate_limit,
)
from core.schemas import ModelConfig


def test_provider_key_maps_antigravity_to_gemini() -> None:
    cfg = ModelConfig(model="antigravity/gemini-2.5-flash", credential="antigravity")

    assert provider_key_for_model_config(cfg) == "gemini"


def test_record_provider_rate_limit_uses_retry_after_with_floor(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANIMAWORKS_PROVIDER_COOLDOWN_FILE", str(tmp_path / "provider_cooldowns.json"))

    cooldown = record_provider_rate_limit(
        "gemini",
        retry_after_s=5.0,
        trigger="heartbeat",
        model="antigravity/gemini-2.5-flash",
        now_ts=1000.0,
    )

    assert cooldown is not None
    assert cooldown.provider == "gemini"
    assert cooldown.remaining_s == 60.0
    assert "RATE_LIMIT_DEFERRED" in format_cooldown_message(cooldown)

    active = get_provider_cooldown("gemini", now_ts=1010.0)
    assert active is not None
    assert active.remaining_s == 50.0

    clear_provider_cooldown("gemini")
    assert get_provider_cooldown("gemini", now_ts=1010.0) is None
