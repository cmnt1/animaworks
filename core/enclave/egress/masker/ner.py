# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Named-entity recognition masking using MeCab (fugashi + IPADIC).

Port of the ``mask()`` routine: proper nouns tagged as person names become
``[MASK-PER]`` and proper nouns tagged as places become ``[MASK-LOC]``. All
other tokens are preserved. When an entity cannot be re-aligned to the source
text the mask fails closed with :class:`MaskerUnavailableError` so callers can
block the whole answer.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class MaskerUnavailableError(RuntimeError):
    """Raised when the masker dependency (fugashi / ipadic) is not available."""


# Replacement for ``名詞,固有名詞,人名`` in IPADIC feature tags.
_PERSON = "[MASK-PER]"
_LOCATION = "[MASK-LOC]"


class NERMasker:
    """Masks person and place proper nouns detected by MeCab (IPADIC)."""

    def __init__(self, tagger: Callable[[str], Any] | None = None) -> None:
        """Create a masker.

        ``tagger`` is an optional injectable callable(text) returning an
        iterable of nodes each exposing ``.surface`` and ``.feature``. When
        omitted, a shared fugashi :class:`~fugashi.Tagger` is used.
        """
        self._injected_tagger = tagger
        self._mecab_tagger: Any | None = None

    def _tagger(self) -> Any:
        if self._injected_tagger is not None:
            return self._injected_tagger
        if self._mecab_tagger is None:
            try:
                import ipadic
                from fugashi import GenericTagger  # type: ignore
            except Exception as exc:  # pragma: no cover - depends on installation
                raise MaskerUnavailableError("fugashi / ipadic (MeCab) is not available") from exc
            self._mecab_tagger = GenericTagger(f"-r /dev/null -d {ipadic.DICDIR}")
        return self._mecab_tagger

    def mask(self, text: str) -> str:
        """Return *text* with detected person/place proper nouns masked.

        Token surfaces are re-aligned to the source text by forward search so
        whitespace or newline-heavy (e.g. pretty-printed) input is masked at
        the correct position. If a mask target cannot be aligned the whole
        text is failed closed.
        """
        tagger = self._tagger()
        masked: list[str] = []
        cursor = 0
        try:
            nodes = tagger(text)
        except Exception as exc:
            raise MaskerUnavailableError("masking failed") from exc

        for node in nodes:
            surface = node.surface
            if surface == "":
                continue
            raw_features = node.feature
            features = raw_features.split(",") if isinstance(raw_features, str) else list(raw_features)
            mask: str | None = None
            if len(features) >= 3 and features[0] == "名詞" and features[1] == "固有名詞":
                if features[2] == "人名":
                    mask = _PERSON
                elif features[2] == "地域":
                    mask = _LOCATION

            position = text.find(surface, cursor)
            if position == -1:
                if mask is not None:
                    raise MaskerUnavailableError("could not align mask target with source text")
                continue

            masked.append(text[cursor:position])
            masked.append(mask if mask is not None else surface)
            cursor = position + len(surface)

        masked.append(text[cursor:])
        return "".join(masked)
