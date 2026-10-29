from __future__ import annotations

"""Server-facing exports for shared anima administration operations."""

from core.anima.admin import DeleteResult, delete_anima_files

__all__ = ["DeleteResult", "delete_anima_files"]
