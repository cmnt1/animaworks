#!/usr/bin/env python3
"""Pre-download the embedding and reranker models used by the test suite.

CI runs the e2e suite with ``HF_HUB_OFFLINE=1`` so that flaky HuggingFace HEAD
requests (HTTP 429) cannot stall a test past its pytest timeout.  That requires
the models to already be present in the cache, which this script guarantees.

The download itself is the one place that must touch the network, so it retries
with exponential backoff to ride out transient rate limiting on a cold cache.
"""

from __future__ import annotations

import os
import sys
import time

# Resolve model names from the application code so this script never drifts
# from the defaults the runtime actually loads.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.memory.rag.singleton import _get_configured_model_name  # noqa: E402
from core.memory.retrieval.reranker import _DEFAULT_MODEL as RERANK_MODEL  # noqa: E402

EMBED_MODEL = _get_configured_model_name()
MODEL_CACHE_DIR = os.environ.get("ANIMAWORKS_MODEL_CACHE_DIR")

BACKOFF_SECONDS = [5, 10, 20, 40, 60, 60, 90, 120]


def _with_retries(label: str, fetch) -> None:
    last_exc: Exception | None = None
    for attempt, delay in enumerate([0, *BACKOFF_SECONDS]):
        if delay:
            print(f"[prefetch] retrying {label} in {delay}s (attempt {attempt})", flush=True)
            time.sleep(delay)
        try:
            fetch()
            print(f"[prefetch] {label}: ready", flush=True)
            return
        except Exception as exc:  # noqa: BLE001 - want to retry any transient failure
            last_exc = exc
            print(f"[prefetch] {label} failed: {exc!r}", flush=True)
    raise SystemExit(f"[prefetch] giving up on {label}: {last_exc!r}")


def _fetch_embedding() -> None:
    from sentence_transformers import SentenceTransformer

    kwargs = {"device": "cpu"}
    if MODEL_CACHE_DIR:
        kwargs["cache_folder"] = MODEL_CACHE_DIR
    SentenceTransformer(EMBED_MODEL, **kwargs)


def _fetch_reranker() -> None:
    from sentence_transformers import CrossEncoder

    CrossEncoder(RERANK_MODEL, device="cpu")


def main() -> None:
    print(f"[prefetch] embedding model: {EMBED_MODEL}", flush=True)
    print(f"[prefetch] reranker model:  {RERANK_MODEL}", flush=True)
    print(f"[prefetch] cache dir:       {MODEL_CACHE_DIR or '(default)'}", flush=True)
    _with_retries("embedding model", _fetch_embedding)
    _with_retries("reranker model", _fetch_reranker)


if __name__ == "__main__":
    main()
