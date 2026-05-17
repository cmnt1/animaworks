from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Direct URL source adapter for Skill Hub imports."""

from pathlib import Path
from urllib.request import Request, urlopen

_MAX_SKILL_MD_BYTES = 512 * 1024


def stage_url_source(source: str, staging_root: Path) -> Path:
    """Fetch a direct SKILL.md URL into *staging_root*."""
    if not source.startswith(("http://", "https://")):
        raise ValueError("URL skill sources must start with http:// or https://")
    req = Request(source, headers={"User-Agent": "AnimaWorks-SkillHub/1.0"})
    with urlopen(req, timeout=15) as response:  # noqa: S310 - explicit user-provided import source
        content = response.read(_MAX_SKILL_MD_BYTES + 1)
    if len(content) > _MAX_SKILL_MD_BYTES:
        raise ValueError("Remote SKILL.md exceeds 512KB")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Remote SKILL.md must be UTF-8 text") from exc
    staged = staging_root / "skill"
    staged.mkdir(parents=True)
    (staged / "SKILL.md").write_text(text, encoding="utf-8")
    return staged
