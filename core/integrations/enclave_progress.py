# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Tool for an anima to write interim progress onto an enclave ask job.

The gateway hands the entry anima a ``job_id``; during long analyses the
anima calls ``enclave_progress`` at milestones so the caller can see, in
real time, that work is still proceeding.  Each line is appended to
``{data_dir}/state/enclave_jobs/{job_id}.progress.jsonl`` and is masked by
the egress pipeline before it is returned to the caller.
"""

from __future__ import annotations

import logging
from typing import Any

from core.enclave.jobs import EnclaveJobStore
from core.i18n import t
from core.integrations._base import dispatch_by_table

logger = logging.getLogger(__name__)

_MAX_TEXT = 500


class _EnclaveDisabledError(ValueError):
    """Raised when a progress tool is called outside an enabled enclave."""


def _resolve_store() -> tuple[EnclaveJobStore, bool]:
    """Return ``(store, enclave_enabled)`` from the current config."""
    from core.config import load_config
    from core.paths import get_data_dir

    config = load_config()
    enabled = config.enclave.enabled is True
    store = EnclaveJobStore(get_data_dir())
    return store, enabled


def enclave_progress(job_id: str, text: str) -> dict[str, Any] | str:
    """Write one interim progress line for a running enclave job."""
    if not isinstance(job_id, str) or not job_id:
        return t("enclave.progress.job_required")
    if not isinstance(text, str) or not text.strip():
        return t("enclave.progress.text_required")

    clipped = text[:_MAX_TEXT]
    try:
        store, enabled = _resolve_store()
        if not enabled:
            return t("enclave.records.only")
        ok, reason = store.write_progress(job_id, clipped)
        if ok:
            return {"written": True, "job_id": job_id}
        if reason == "not_found":
            return t("enclave.progress.not_found", job_id=job_id)
        return t("enclave.progress.not_running")
    except Exception as exc:
        logger.warning("enclave progress: write failed for job %s (%s)", job_id, type(exc).__name__)
        return t("enclave.progress.unavailable")


def _dispatch(args: dict[str, Any]) -> dict[str, Any] | str:
    return enclave_progress(
        job_id=args.get("job_id", "") or args.get("job-id", ""),
        text=args.get("text", ""),
    )


_DISPATCH_HANDLERS = {
    "enclave_progress": _dispatch,
}


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Dispatch a progress tool call by its schema name."""
    return dispatch_by_table(_DISPATCH_HANDLERS, name, args)


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return the progress tool schema."""
    return [
        {
            "name": "enclave_progress",
            "description": t("enclave.progress.schema_description"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": t("enclave.progress.schema_job_id")},
                    "text": {"type": "string", "description": t("enclave.progress.schema_text")},
                },
                "required": ["job_id", "text"],
            },
        },
    ]


def cli_main(argv: list[str] | None = None) -> None:
    """Run ``animaworks-tool enclave_progress enclave_progress --job-id ... --text ...``."""
    from core.integrations._base import schema_cli_main

    schema_cli_main("animaworks-tool enclave_progress", get_tool_schemas(), dispatch, argv)


__all__ = ["cli_main", "dispatch", "enclave_progress", "get_tool_schemas"]
