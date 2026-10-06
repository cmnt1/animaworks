# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for record-fact masking (rule-based, domain-generic).

Inputs use generic business wording (customer service, shipping, contracts).
"""

from __future__ import annotations

import pytest

from core.enclave.egress.masker.facts import mask_record_facts


@pytest.mark.parametrize(
    "text",
    [
        "2016/5/26",
        "2022-10-14",
        "2022年10月14日",
        "２０２６／５／２６",
        "5/26",
        "10月14日",
    ],
)
def test_masks_calendar_dates(text: str) -> None:
    assert mask_record_facts(text) == "[MASK-DATE]"


def test_masks_measurement_values() -> None:
    assert mask_record_facts("在庫35、残高 7.2、温度: 25.5") == "[MASK-VAL]、[MASK-VAL]、[MASK-VAL]"


def test_keeps_context_without_number() -> None:
    assert mask_record_facts("在庫が少なくなったため再発注") == "在庫が少なくなったため再発注"


def test_masks_identifiers_and_contacts_but_keeps_context() -> None:
    text = (
        "顧客名: 山田太郎、顧客ID: C-0042、電話 090-1234-5678、"
        "mail tanaka@example.test、〒123-4567、住所: 東京都千代田区中央1-2-3。"
        "弊社は速達で発送を依頼。"
    )
    result = mask_record_facts(text)
    for marker in ["山田太郎", "C-0042", "090-1234-5678", "tanaka@example.test", "123-4567", "東京都千代田区中央1-2-3"]:
        assert marker not in result
    for mask in ["[MASK-PER]", "[MASK-ID]", "[MASK-PHONE]", "[MASK-EMAIL]", "[MASK-POSTAL]", "[MASK-ADDR]"]:
        assert mask in result
    assert "弊社は速達で発送を依頼。" in result


def test_masks_honorific_person_name_while_keeping_context() -> None:
    assert mask_record_facts("山田太郎さんは速達の件で相談した。") == "[MASK-PER]さんは速達の件で相談した。"


def test_masks_site_name() -> None:
    assert mask_record_facts("受注は名古屋営業所で完了した") == "[MASK-LOC]で完了した"
