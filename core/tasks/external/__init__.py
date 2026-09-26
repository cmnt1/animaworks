# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""External tasks snapshot store and multi-source collector skeleton."""

from core.tasks.external.collector import CredentialNotFoundError, collect_all
from core.tasks.external.models import ExternalTask, Snapshot, SourceHealth
from core.tasks.external.store import ExternalTaskStore

__all__ = [
    "CredentialNotFoundError",
    "ExternalTask",
    "ExternalTaskStore",
    "Snapshot",
    "SourceHealth",
    "collect_all",
]
