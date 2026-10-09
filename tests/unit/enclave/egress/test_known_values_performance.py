# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Differential and performance tests for known-value matching."""

from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path

import pytest

from core.enclave.egress.config import load_egress_config
from core.enclave.egress.models import Fact
from core.enclave.egress.stages import (
    _add_known,
    _add_known_buckets,
    _redact_known,
    _redact_known_patterns,
    run_stage,
)

_RANDOM_CHARS = (
    "山田東京千代田区漢字ひらがなカタカナタロウサンプル"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    "ＡＢＣＤＥＦ１２３４５６"
    "ぁぃぅぇぉアイウエオｶﾀｶﾅ①ﬃ"
    " 　\t\n-_/.:"
)


def _legacy_result(text: str, values: list[str], *, min_length: int = 2, ngram: int = 8) -> tuple[str, int]:
    known: set[str] = set()
    for value in values:
        _add_known(known, value, min_length, ngram)
    if not known:
        return text, 0
    alternation = "|".join(re.escape(value) for value in sorted(known, key=len, reverse=True))
    return _redact_known(text, re.compile(f"(?=({alternation}))"))


def test_known_value_matcher_matches_legacy_regex_for_randomized_inputs() -> None:
    rng = random.Random(0xE6C1A7E)

    for _ in range(300):
        text = "".join(rng.choice(_RANDOM_CHARS) for _ in range(rng.randint(0, 160)))
        values = [
            "".join(rng.choice(_RANDOM_CHARS) for _ in range(rng.randint(1, 20))) for _ in range(rng.randint(0, 12))
        ]
        if text:
            # Guarantee a mixture of direct, overlapping, and normalized hits.
            first = rng.randrange(len(text))
            values.append(text[first : first + rng.randint(2, 12)])
            if len(text) > 4:
                second = rng.randrange(len(text) - 1)
                values.append(text[second : second + rng.randint(2, 10)])

        legacy = _legacy_result(text, values)
        buckets: dict[int, set[str]] = {}
        for value in values:
            _add_known_buckets(buckets, value, 2, 8)
        actual = _redact_known_patterns(text, buckets)
        assert actual == legacy


@pytest.mark.slow
@pytest.mark.performance
def test_known_value_matching_performance_200k_values_20kb_text(tmp_path: Path) -> None:
    values_path = tmp_path / "values.jsonl"
    with values_path.open("w", encoding="utf-8") as stream:
        for index in range(200_000):
            value = f"v{index:06d}xy"
            stream.write(json.dumps({"value": value}) + "\n")

    stage = load_egress_config(
        {
            "stages": [
                {
                    "type": "known_values",
                    "sources": [{"path": "values.jsonl", "format": "jsonl", "fields": ["value"]}],
                    "min_length": 2,
                    "ngram": 8,
                }
            ]
        }
    ).stages[0]
    text = "z" * 20_000

    started = time.perf_counter()
    result, count = run_stage(stage, [Fact(text, [])], data_dir=tmp_path, case_id="performance")
    elapsed = time.perf_counter() - started

    assert elapsed < 3.0
    assert result[0].fact == text
    assert count == 0


def test_long_free_text_values_stay_fast() -> None:
    """Many long values (e.g. transcripts) must not explode the match lengths."""
    import random
    import time

    from core.enclave.egress.stages import _add_known_buckets, _redact_known_patterns

    rng = random.Random(7)
    alphabet = "あいうえおかきくけこさしすせそたちつてとなにぬねの漢字検査アイウエオ0123456789"
    known: dict[int, set[str]] = {}
    values = ["".join(rng.choice(alphabet) for _ in range(rng.randint(100, 2000))) for _ in range(300)]
    for value in values:
        _add_known_buckets(known, value, 2, 8)
    assert len(known) <= 8
    text = values[0][:500] + ("x" * 19_000) + values[1][-300:]
    started = time.perf_counter()
    redacted, count = _redact_known_patterns(text, known)
    assert time.perf_counter() - started < 3.0
    assert values[0][:500] not in redacted
    assert values[1][-300:] not in redacted
    assert count >= 2
