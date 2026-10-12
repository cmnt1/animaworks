# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Built-in masker for the egress pipeline.

Modules (grouped here):
- ``ner``: MeCab (fugashi + ipadic) named-entity masking of person/place names.
- ``facts``: rule-based masking of record-level PII.
- ``log_pii``: masking of URLs, contexts, and audit details.
- ``dispatch``: profile selection (``default`` = ner → record_facts → log_pii).
"""

from __future__ import annotations

from core.enclave.egress.masker.dispatch import mask_text
from core.enclave.egress.masker.ner import MaskerUnavailableError, NERMasker

__all__ = ["MaskerUnavailableError", "NERMasker", "mask_text"]
