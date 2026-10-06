# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Rule-based masking of record facts.

Renamed from ``mask_record_facts`` in the ported module. Domain-specific
labels were replaced with generic ones (customer service, shipping, contracts,
etc.) but every original rule is preserved: calendar dates, identifiers,
honorific names, contact details, addresses, measurement values, and place
(site) names are replaced with ``[MASK-*]`` tokens while the surrounding
context is kept.
"""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)


def _kata_to_hira(ch: str) -> str:
    """Convert one katakana character to its hiragana equivalent."""
    code = ord(ch)
    if 0x30A1 <= code <= 0x30F6:
        return chr(code - 0x60)
    if code in (0x30FD, 0x30FE):  # ヽ・ヾ -> ゝ・ゞ
        return chr(code - 0x60)
    return ch


def normalize_known_value(value: str) -> str:
    """Normalize a value for matching: NFKC, strip whitespace, katakana to
    hiragana, lowercase."""
    out: list[str] = []
    for ch in unicodedata.normalize("NFKC", value):
        if ch.isspace():
            continue
        out.append(_kata_to_hira(ch).lower())
    return "".join(out)


# Calendar dates (western, Japanese, full-width) become [MASK-DATE].
_DATE_PATTERNS = [
    r"(?<!\d)(?:19|20)\d{2}年(?:0?[1-9]|1[0-2])月(?:0?[1-9]|[12]\d|3[01])日",
    r"(?<!\d)(?:19|20)\d{2}[/-](?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])(?!\d)",
    r"(?<![０-９])(?:１９|２０)[０-９]{2}[／－][０-９]{1,2}[／－][０-９]{1,2}(?![０-９])",
    r"(?<![\d/])(?:0?[1-9]|1[0-2])月(?:0?[1-9]|[12]\d|3[01])日",
    r"(?<![\d/])(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])(?![\d/])",
]
# Script variants for [一-龯] style classes used across patterns.
_KANJI = r"一-龯々"

# Identifier and contact-detail patterns -> backing reference number / person /
# e-mail / phone / postal code / address.
_IDENTIFIER_PATTERNS = [
    (
        r"((?:顧客|customer|お客様)\s*(?:ID|ＩＤ|番号)\s*[:：#]?\s*)[A-Za-z0-9Ａ-Ｚａ-ｚ０-９_\-\/／]+",
        r"\g<1>[MASK-ID]",
    ),
    (
        r"((?:台帳\s*(?:ID|ＩＤ|番号)|ledger\s*(?:id|number)|ref_no)\s*[:：#]?\s*)[A-Za-z0-9Ａ-Ｚａ-ｚ０-９_\-\/／]+",
        r"\g<1>[MASK-ID]",
    ),
    (
        r"((?:氏名|お名前|顧客名)\s*[:：]\s*)[" + _KANJI + r"ぁ-んァ-ヶーA-Za-z・　 ]{2,40}",
        r"\g<1>[MASK-PER]",
    ),
    (
        r"[" + _KANJI + r"]{2,8}(?=(?:さん|様|氏|先生)(?:[はがをにへ、。\s]|$))",
        "[MASK-PER]",
    ),
    (
        r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9._%+-])",
        "[MASK-EMAIL]",
    ),
    (
        r"(?<!\d)(?:\+81[- ]?(?:0)?|0)\d{1,4}[- ]?\d{1,4}[- ]?\d{3,4}(?!\d)",
        "[MASK-PHONE]",
    ),
    (r"(?:〒\s*)?\d{3}[-ー]\d{4}", "[MASK-POSTAL]"),
    (
        r"((?:住所|所在地)\s*[:：]\s*)[^\n、。]{3,100}",
        r"\g<1>[MASK-ADDR]",
    ),
]

# Measurement values (a known label followed by a number) -> [MASK-VAL].
_MEASUREMENT_LABELS = (
    r"(?:残高|在庫|個数|数量|金額|距離|重量|面積|温度|湿度|風速|酸度|硬度|粘度|圧力|"
    r"血流|脈拍|呼吸数|視力|聴力|身長|体重|比重|密度|濃度|純度|等級|値|度数|回数|件数|冊数)"
)
_VALUE_RE = re.compile(
    r"(?<!\w)" + _MEASUREMENT_LABELS + r"\s*(?:[:：=]\s*)?[<>]?\s*-?\d+(?:\.\d+)?",
    re.IGNORECASE,
)

# Site (place) names ending in a facility suffix, optionally with a
# department suffix, become [MASK-LOC].
_FACILITY_SUFFIX = (
    r"(?:物流センター|配送センター|データセンター|ビジネスセンター|総合センター|"
    r"メディカルセンター|研修センター|営業所|支店|本社|本店|工場|倉庫|事業所|事務所|"
    r"学校|大学|高校|アカデミー)"
)
_DEPARTMENT_SUFFIX = r"(?:[" + _KANJI + r"ぁ-んァ-ヶー]{1,8}(?:部|課|室|科|センター))?"
_FACILITY_RE = re.compile(
    r"(^|[\s、。・「」（）()\nはをにへでの])"
    r"([" + _KANJI + r"ぁ-んァ-ヶーA-Za-z0-9０-９第]{1,40}?" + _FACILITY_SUFFIX + _DEPARTMENT_SUFFIX + r")"
)

_IDENTIFIER_COMPILED = [(re.compile(p, re.IGNORECASE), r) for p, r in _IDENTIFIER_PATTERNS]
_DATE_COMPILED = [re.compile(p) for p in _DATE_PATTERNS]


def _mask_dates(text: str) -> str:
    for pattern in _DATE_COMPILED:
        text = pattern.sub("[MASK-DATE]", text)
    return text


def _mask_identifiers(text: str) -> str:
    for pattern, replacement in _IDENTIFIER_COMPILED:
        text = pattern.sub(replacement, text)
    return text


def mask_record_facts(text: str) -> str:
    """Mask record-level personal information in *text*.

    Dates, identifiers, names, contact details, addresses, measurement
    values, and place names are replaced with ``[MASK-*]`` tokens while the
    surrounding (contextual) wording is preserved. Raises ``re.error`` (a
    ``ValueError``) if a pattern is malformed so callers can fail closed.
    """
    text = _mask_dates(text)
    text = _mask_identifiers(text)
    text = _VALUE_RE.sub("[MASK-VAL]", text)
    text = _FACILITY_RE.sub(r"\g<1>[MASK-LOC]", text)
    return text
