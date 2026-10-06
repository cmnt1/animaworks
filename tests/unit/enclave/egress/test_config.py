# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the egress configuration model."""

from __future__ import annotations

import pytest

from core.enclave.egress.config import EgressConfigError, load_egress_config


def test_valid_config_with_default_limits() -> None:
    cfg = load_egress_config({"stages": [{"type": "regex_denylist", "patterns": []}]})
    assert cfg.max_facts == 50
    assert cfg.max_fact_chars == 2000


def test_custom_limits() -> None:
    cfg = load_egress_config(
        {"stages": [{"type": "masker", "profile": "default"}], "max_facts": 3, "max_fact_chars": 100}
    )
    assert cfg.max_facts == 3
    assert cfg.max_fact_chars == 100


def test_all_stage_types_parse() -> None:
    cfg = load_egress_config(
        {
            "stages": [
                {"type": "pseudonymize_ids", "patterns": [{"name": "x", "regex": r"\bx\d{2}\b", "prefix": "P"}]},
                {"type": "known_values", "sources": [], "min_length": 2, "ngram": 8},
                {"type": "masker", "profile": "default"},
                {"type": "regex_denylist", "patterns": [{"regex": r"\d+", "action": "redact"}]},
                {"type": "command", "argv": ["true"], "timeout_s": 5},
            ]
        }
    )
    assert len(cfg.stages) == 5


def test_empty_stages_is_error() -> None:
    with pytest.raises(EgressConfigError):
        load_egress_config({"stages": []})


def test_unknown_stage_type_is_error() -> None:
    with pytest.raises(EgressConfigError):
        load_egress_config({"stages": [{"type": "bogus"}]})


def test_bad_stage_shape_is_error() -> None:
    with pytest.raises(EgressConfigError):
        load_egress_config({"stages": [{"type": "command"}]})
