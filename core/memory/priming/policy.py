from __future__ import annotations

"""Small, model-independent policy resolved before priming does any searches."""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PrimingPolicy:
    max_tokens: int = 2000


def resolve_priming_policy() -> PrimingPolicy:
    from core.config import load_config

    try:
        config = load_config().priming
        maximum = config.max_tokens
    except Exception:
        logger.debug("Using default priming policy", exc_info=True)
        maximum = 2000
    return PrimingPolicy(max_tokens=maximum if isinstance(maximum, int) and maximum >= 200 else 2000)
