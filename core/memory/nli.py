from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Shared Natural Language Inference helper for memory consistency checks."""

import logging

logger = logging.getLogger("animaworks.memory.nli")


class SharedNLIModel:
    """Lazy wrapper around the multilingual NLI classifier.

    This helper is intentionally small: contradiction detection needs local
    entailment/contradiction labels, while LLM review stays in the detector.
    """

    NLI_MODEL = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"

    def __init__(self) -> None:
        self._nli_pipeline = None
        self._nli_available = True

    def _load_nli_model(self) -> None:
        """Load the NLI model. GPU -> CPU fallback. On failure, NLI is skipped."""
        try:
            from transformers import pipeline as hf_pipeline

            try:
                self._nli_pipeline = hf_pipeline(
                    "text-classification",
                    model=self.NLI_MODEL,
                    device=0,
                )
                logger.info("NLI model loaded on GPU")
            except Exception:
                self._nli_pipeline = hf_pipeline(
                    "text-classification",
                    model=self.NLI_MODEL,
                    device=-1,
                )
                logger.info("NLI model loaded on CPU (GPU unavailable)")
        except Exception:
            logger.warning("NLI model load failed; NLI checks disabled")
            self._nli_available = False

    def check(self, hypothesis: str, premise: str) -> tuple[str, float]:
        """Run NLI inference on a premise-hypothesis pair."""
        if self._nli_pipeline is None and self._nli_available:
            self._load_nli_model()
        if not self._nli_available or self._nli_pipeline is None:
            return ("neutral", 0.0)
        try:
            result = self._nli_pipeline(
                f"{premise} [SEP] {hypothesis}",
                truncation=True,
            )
            label = str(result[0]["label"]).lower()
            score = float(result[0]["score"])
            return (label, score)
        except Exception as exc:
            logger.warning("NLI check failed: %s", exc)
            return ("neutral", 0.0)
