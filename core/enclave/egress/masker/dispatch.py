# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Profile dispatch for the built-in masker.

``profile: "default"`` applies NER → record-facts → log-PII (URLs) in order.
``profile: "personal_dates"`` is the same but masks only dates that point at a
person (birth dates, era dates, years before 2015), keeping event timestamps.
"""

from __future__ import annotations

import logging

from core.enclave.egress.masker.facts import mask_record_facts
from core.enclave.egress.masker.log_pii import mask_inline_urls
from core.enclave.egress.masker.ner import MaskerUnavailableError, NERMasker

logger = logging.getLogger(__name__)


def mask_text(profile: str, text: str) -> str:
    """Apply the built-in masker configured by *profile* to *text*."""
    if profile == "default":
        return _mask_default(text)
    if profile == "personal_dates":
        return _mask_default(text, dates="personal")
    raise ValueError(f"unknown masker profile: {profile!r}")


def _mask_default(text: str, *, dates: str = "all") -> str:
    ner = NERMasker()
    text = ner.mask(text)
    text = mask_record_facts(text, dates=dates)
    text = mask_inline_urls(text)
    return text


__all__ = ["MaskerUnavailableError", "mask_text"]
