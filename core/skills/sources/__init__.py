from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Skill Hub source adapters."""

from core.skills.sources.github import stage_github_source
from core.skills.sources.local import stage_local_source
from core.skills.sources.url import stage_url_source

__all__ = ["stage_github_source", "stage_local_source", "stage_url_source"]
