# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the NER masker (MeCab person/place name masking).

Rules are ported from the original implementation: proper nouns tagged as a
person become ``[MASK-PER]`` and proper nouns tagged as a place become
``[MASK-LOC]``; other tokens are preserved. An injectable fake tagger is used
for deterministic rule tests, plus one real-fugashi integration test.
"""

from __future__ import annotations

import builtins
import sys
from typing import Any

import pytest

from core.enclave.egress.masker import MaskerUnavailableError, NERMasker, mask_text


class _Node:
    def __init__(self, surface: str, feature: str) -> None:
        self.surface = surface
        self.feature = feature


class _FakeTagger:
    def __init__(self, nodes: list[_Node]) -> None:
        self.nodes = nodes

    def __call__(self, _text: str) -> list[_Node]:
        return self.nodes


def _masker_with(*nodes: _Node) -> NERMasker:
    return NERMasker(tagger=_FakeTagger(list(nodes)))


PERSON = "名詞,固有名詞,人名,一般,*,*,*,*,*"
PLACE = "名詞,固有名詞,地域,一般,*,*,*,*,*"


def test_masks_person_name() -> None:
    masker = _masker_with(
        _Node("田中太郎", PERSON),
        _Node("さん", "名詞,接尾,人名,*,*,*,*,*,*"),
    )
    assert masker.mask("田中太郎さん") == "[MASK-PER]さん"


def test_masks_location_name() -> None:
    masker = _masker_with(
        _Node("東京", PLACE),
        _Node("に", "助詞,格助詞,一般,*,*,*,*,*,*"),
        _Node("住む", "動詞,自立,*,*,五段・マ行,基本形,*,*,*"),
    )
    assert masker.mask("東京に住む") == "[MASK-LOC]に住む"


def test_masks_multiple_entities_with_correct_offsets() -> None:
    masker = _masker_with(
        _Node("田中太郎", PERSON),
        _Node("は", "助詞,係助詞,*,*,*,*,*,*,*"),
        _Node("東京", PLACE),
        _Node("に", "助詞,格助詞,一般,*,*,*,*,*,*"),
        _Node("住んでいます", "動詞,自立,*,*,*,*,*,*,*"),
    )
    assert masker.mask("田中太郎は東京に住んでいます") == "[MASK-PER]は[MASK-LOC]に住んでいます"


def test_masks_entity_at_end_of_text() -> None:
    masker = _masker_with(
        _Node("ここ", "名詞,代名詞,一般,*,*,*,*,*,*"),
        _Node("は", "助詞,係助詞,*,*,*,*,*,*,*"),
        _Node("大阪", PLACE),
    )
    assert masker.mask("ここは大阪") == "ここは[MASK-LOC]"


def test_masks_correct_position_when_tokens_separated_by_whitespace() -> None:
    # Pretty-printed JSON: token alignment must not drift with whitespace.
    text = '{\n    "s_cont_1": "田中太郎",\n    "s_cont_2": "東京"\n}'
    masker = _masker_with(
        _Node('{\n    "s_cont_1": "', "記号,一般,*,*,*,*,*,*,*"),
        _Node("田中太郎", PERSON),
        _Node('",\n    "s_cont_2": "', "記号,一般,*,*,*,*,*,*,*"),
        _Node("東京", PLACE),
        _Node('"\n}', "記号,一般,*,*,*,*,*,*,*"),
    )
    result = masker.mask(text)
    assert '"s_cont_1": "[MASK-PER]"' in result
    assert '"s_cont_2": "[MASK-LOC]"' in result
    assert "田中太郎" not in result
    assert "東京" not in result


def test_does_not_mask_non_proper_nouns() -> None:
    masker = _masker_with(
        _Node("情報", "名詞,一般,*,*,*,*,*,*,*"),
        _Node("を", "助詞,格助詞,一般,*,*,*,*,*,*"),
        _Node("処理", "名詞,サ変接続,*,*,*,*,*,*,*"),
        _Node("する", "動詞,自立,*,*,サ変・スル,基本形,*,*,*"),
    )
    assert masker.mask("情報を処理する") == "情報を処理する"


def test_does_not_mask_organization_proper_nouns() -> None:
    masker = _masker_with(
        _Node("マルセイ", "名詞,固有名詞,組織,*,*,*,*,*,*"),
        _Node("は", "助詞,係助詞,*,*,*,*,*,*,*"),
        _Node("大企業", "名詞,一般,*,*,*,*,*,*,*"),
    )
    assert masker.mask("マルセイは大企業") == "マルセイは大企業"


def test_handles_short_feature_array() -> None:
    masker = _masker_with(
        _Node("テスト", "名詞,固有名詞"),
        _Node("です", "助動詞,*,*,*,*,*,*,*,*"),
    )
    assert masker.mask("テストです") == "テストです"


def test_masks_consecutive_proper_nouns() -> None:
    masker = _masker_with(
        _Node("山田", "名詞,固有名詞,人名,姓,*,*,*,*,*"),
        _Node("花子", "名詞,固有名詞,人名,名,*,*,*,*,*"),
        _Node("です", "助動詞,*,*,*,*,*,*,*,*"),
    )
    assert masker.mask("山田花子です") == "[MASK-PER][MASK-PER]です"


def test_returns_original_when_no_entities() -> None:
    masker = _masker_with(
        _Node("今日", "名詞,副詞可能,*,*,*,*,*,*,*"),
        _Node("は", "助詞,係助詞,*,*,*,*,*,*,*"),
        _Node("良い天気", "形容詞,自立,*,*,*,*,*,*,*"),
    )
    assert masker.mask("今日は良い天気") == "今日は良い天気"


def test_handles_empty_text() -> None:
    masker = _masker_with()
    assert masker.mask("") == ""


def test_alignment_failure_is_fail_closed() -> None:
    masker = _masker_with(_Node("別人", PERSON))
    with pytest.raises(MaskerUnavailableError):
        masker.mask("佐藤花子さん")


def test_unavailable_when_fugashi_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "fugashi", raising=False)
    monkeypatch.delitem(sys.modules, "ipadic", raising=False)
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "fugashi":
            raise ImportError("no fugashi")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    masker = NERMasker()
    with pytest.raises(MaskerUnavailableError):
        masker.mask("田中太郎")


def test_real_fugashi_masks_person_and_place() -> None:
    masker = NERMasker()
    result = masker.mask("田中太郎は東京に住んでいます")
    assert "[MASK-PER]" in result
    assert "[MASK-LOC]" in result
    assert "田中" not in result
    assert "東京" not in result


def test_default_masker_preserves_source_paths_and_code_identifiers() -> None:
    text = "原因は app/Services/AI/AIRequestBuilder.php:101 の分岐で、few_shot_count が 0 のとき system_body が空になる"
    try:
        result = mask_text("default", text)
    except MaskerUnavailableError as exc:
        if "not available" in str(exc):
            pytest.skip("fugashi / ipadic are not available")
        raise

    for code_token in (
        "app/Services/AI/AIRequestBuilder.php:101",
        "few_shot_count",
        "system_body",
    ):
        assert code_token in result
