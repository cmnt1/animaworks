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

logger = logging.getLogger(__name__)


# Calendar dates (western, Japanese, full-width) become [MASK-DATE].
_DATE_PATTERNS = [
    r"(?<!\d)(?:19|20)\d{2}年(?:0?[1-9]|1[0-2])月(?:0?[1-9]|[12]\d|3[01])日",
    r"(?<!\d)(?:19|20)\d{2}[/-](?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])(?!\d)",
    r"(?<![０-９])(?:１９|２０)[０-９]{2}[／－][０-９]{1,2}[／－][０-９]{1,2}(?![０-９])",
    r"(?<![\d/])(?:0?[1-9]|1[0-2])月(?:0?[1-9]|[12]\d|3[01])日",
    r"(?<![\d/])(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])(?![\d/])",
]
# Dates that identify a person: a date next to a birth label, a Japanese era
# date (昭和/平成/... birthdays), or any full date before _OLD_YEAR_LIMIT, which
# predates every system event and so is almost always a birth date.
_PERSONAL_DATE_LABEL = r"(?:生年月日|誕生日|生まれ|出生|date\s+of\s+birth|birth\s*date|birthday|DOB)"
_ANY_DATE = (
    r"(?:(?:明治|大正|昭和|平成|令和|[MTSHR])\s*(?:元|\d{1,2})[年./-]\s*\d{1,2}[月./-]\s*\d{1,2}日?"
    r"|(?:19|20)\d{2}\s*[年/.-]\s*\d{1,2}\s*[月/.-]\s*\d{1,2}日?"
    r"|(?:１９|２０)[０-９]{2}[／－][０-９]{1,2}[／－][０-９]{1,2}"
    r"|\d{1,2}月\d{1,2}日)"
)
_PERSONAL_DATE_PATTERNS = [
    # label before the date: 生年月日: 1980年5月3日 / birthday 1980-05-03
    re.compile(r"(" + _PERSONAL_DATE_LABEL + r"[^\d\n明大昭平令MTSHR１２]{0,6})" + _ANY_DATE, re.IGNORECASE),
    # date followed by a birth word: 1980/5/3生まれ / 昭和55年5月3日生
    re.compile(_ANY_DATE + r"(?=\s*(?:生まれ|生|出生))"),
    # Japanese era dates on their own.
    re.compile(r"(?:明治|大正|昭和|平成)\s*(?:元|\d{1,2})年\s*\d{1,2}月\s*\d{1,2}日"),
]
_OLD_YEAR_LIMIT = 2015
_FULL_DATE_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*[年/.-]\s*\d{1,2}\s*[月/.-]\s*\d{1,2}日?(?!\d)")
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
        # Not glued to letters (record IDs such as TK000001); digit count is checked in _phone_repl.
        r"(?<![\dA-Za-z])(?:\+81[- ]?(?:0)?|0)\d{1,4}[- ]?\d{1,4}[- ]?\d{3,4}(?![\dA-Za-z])",
        lambda m: _phone_repl(m),
    ),
    (r"(?:〒\s*)?(?<![\d:])\d{3}[-ー]\d{4}(?!\d)", "[MASK-POSTAL]"),
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


def _phone_repl(match: re.Match[str]) -> str:
    """Mask only plausible phone numbers: 10-11 digits, or +81 with 9-10 national digits."""
    raw = match.group(0)
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+81"):
        national = digits[2:].removeprefix("0")
        plausible = 9 <= len(national) <= 10
    else:
        plausible = 10 <= len(digits) <= 11
    return "[MASK-PHONE]" if plausible else raw


_IDENTIFIER_COMPILED = [(re.compile(p, re.IGNORECASE), r) for p, r in _IDENTIFIER_PATTERNS]
_DATE_COMPILED = [re.compile(p) for p in _DATE_PATTERNS]


def _mask_dates(text: str) -> str:
    for pattern in _DATE_COMPILED:
        text = pattern.sub("[MASK-DATE]", text)
    return text


def _mask_personal_dates(text: str) -> str:
    """Mask only dates that point at a person; keep event and log timestamps."""
    labeled, birth_suffix, era = _PERSONAL_DATE_PATTERNS
    text = labeled.sub(lambda m: m.group(1) + "[MASK-DATE]", text)
    text = birth_suffix.sub("[MASK-DATE]", text)
    text = era.sub("[MASK-DATE]", text)
    return _FULL_DATE_RE.sub(lambda m: "[MASK-DATE]" if int(m.group(1)) < _OLD_YEAR_LIMIT else m.group(0), text)


def _mask_identifiers(text: str) -> str:
    for pattern, replacement in _IDENTIFIER_COMPILED:
        text = pattern.sub(replacement, text)
    return text


def mask_record_facts(text: str, *, dates: str = "all") -> str:
    """Mask record-level personal information in *text*.

    Dates, identifiers, names, contact details, addresses, measurement
    values, and place names are replaced with ``[MASK-*]`` tokens while the
    surrounding (contextual) wording is preserved. Raises ``re.error`` (a
    ``ValueError``) if a pattern is malformed so callers can fail closed.
    """
    text = _mask_personal_dates(text) if dates == "personal" else _mask_dates(text)
    text = _mask_identifiers(text)
    text = _VALUE_RE.sub("[MASK-VAL]", text)
    text = _FACILITY_RE.sub(r"\g<1>[MASK-LOC]", text)
    return text
