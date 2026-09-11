from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Lifecycle helpers.

Production system crons are owned by ``core.supervisor``.  This package
retains the shared lifecycle sub-modules used there:

- ``system_consolidation``: daily/weekly consolidation pipeline helpers
- ``knowledge_correction``: self-correction helpers used by consolidation
- ``anima_merge``: used by ``cli/commands/anima_merge``
"""
