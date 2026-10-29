from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Filesystem checks for built-in Anima skills."""

from pathlib import Path


def has_newstaff_skill(anima_dir: Path) -> bool:
    """Return whether an Anima has the newstaff hiring-permission skill."""
    skills_dir = anima_dir / "skills"
    return (skills_dir / "newstaff" / "SKILL.md").is_file() or (skills_dir / "newstaff.md").is_file()
