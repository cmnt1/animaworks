from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import json

import pytest
from pydantic import ValidationError

from core.config.models import AnimaWorksConfig, PhoneConfig


def test_phone_config_defaults() -> None:
    config = PhoneConfig()

    assert config.enabled is False
    assert config.anima == "aoi"
    assert config.public_base_url == "https://zoomhook.kk-a.jp"
    assert config.from_number == "+16073257655"
    assert config.owner_numbers == ["+819060943763"]
    assert config.from_person == "human"
    assert config.thread_id == "phone"
    assert config.pin_vault_key == "AOI_PHONE_PIN"
    assert config.account_sid_vault_key == "TWILIO_ACCOUNT_SID"
    assert config.auth_token_vault_key == "TWILIO_AUTH_TOKEN"
    assert config.alert_max_attempts == 3
    assert config.alert_retry_interval_sec == 120
    assert config.turn_timeout_sec == 300
    assert config.turn_end_silence_ms == 2000


def test_phone_config_is_available_and_roundtrips_with_global_config() -> None:
    config = AnimaWorksConfig(phone=PhoneConfig(enabled=True, owner_numbers=["+100", "+200"]))

    serialized = json.loads(config.model_dump_json())
    restored = AnimaWorksConfig.model_validate(serialized)

    assert restored.phone.enabled is True
    assert restored.phone.owner_numbers == ["+100", "+200"]


def test_phone_config_rejects_invalid_retry_limits() -> None:
    with pytest.raises(ValidationError):
        PhoneConfig(alert_max_attempts=0)
    with pytest.raises(ValidationError):
        PhoneConfig(turn_timeout_sec=0)
    with pytest.raises(ValidationError):
        PhoneConfig(turn_end_silence_ms=299)
    with pytest.raises(ValidationError):
        PhoneConfig(turn_end_silence_ms=5001)
