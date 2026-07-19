# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Company membership and cross-company boundary helpers.

Membership is deliberately resolved from each anima's ``status.json`` on
every call.  This keeps company assignment changes effective without a server
restart and avoids making the synchronized ``config.json`` entry authoritative.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.config.models import read_anima_company

logger = logging.getLogger(__name__)


def _resolve_data_dir(data_dir: Path | None) -> Path:
    if data_dir is not None:
        return data_dir
    from core.paths import get_data_dir

    return get_data_dir()


def _resolve_animas_dir(
    *,
    data_dir: Path | None,
    animas_dir: Path | None,
) -> Path:
    if animas_dir is not None:
        return animas_dir
    return _resolve_data_dir(data_dir) / "animas"


def _company_dir(company_name: str, data_dir: Path) -> Path | None:
    """Resolve a company directory without allowing membership path escape."""
    companies_dir = (data_dir / "companies").resolve()
    candidate = (companies_dir / company_name).resolve()
    if candidate.parent != companies_dir:
        logger.warning("Ignoring unsafe company name: %r", company_name)
        return None
    return candidate


def read_company_config(
    company_name: str,
    *,
    data_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Read ``companies/<name>/company.json`` when it is a JSON object."""
    if not isinstance(company_name, str) or not company_name.strip():
        return None
    root = _resolve_data_dir(data_dir)
    directory = _company_dir(company_name.strip(), root)
    if directory is None:
        return None
    config_path = directory / "company.json"
    if not config_path.is_file():
        return None
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read %s: %s", config_path, exc)
        return None
    return value if isinstance(value, dict) else None


def get_company(
    anima_name: str,
    *,
    data_dir: Path | None = None,
    animas_dir: Path | None = None,
) -> str | None:
    """Return an anima's current company membership from disk."""
    if not isinstance(anima_name, str) or not anima_name:
        return None
    root = _resolve_animas_dir(data_dir=data_dir, animas_dir=animas_dir)
    candidate = (root / anima_name).resolve()
    if candidate.parent != root.resolve():
        logger.warning("Ignoring unsafe anima name: %r", anima_name)
        return None
    return read_anima_company(candidate)


def get_company_display_name(
    company_name: str,
    *,
    data_dir: Path | None = None,
) -> str:
    """Return a company's display name, falling back to its directory name."""
    config = read_company_config(company_name, data_dir=data_dir)
    if config is not None:
        display_name = config.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()
    return company_name


def is_cross_company(
    anima_a: str,
    anima_b: str,
    *,
    data_dir: Path | None = None,
    animas_dir: Path | None = None,
) -> bool:
    """Return whether two assigned animas belong to different companies.

    An unassigned anima remains unrestricted for legacy compatibility.
    """
    root = _resolve_animas_dir(data_dir=data_dir, animas_dir=animas_dir)
    company_a = get_company(anima_a, animas_dir=root)
    company_b = get_company(anima_b, animas_dir=root)
    return company_a is not None and company_b is not None and company_a != company_b
