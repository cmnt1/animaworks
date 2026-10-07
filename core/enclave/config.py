# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Configuration models for enclave mode."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class EnclaveDatasetConfig(BaseModel):
    """A JSONL dataset available to an isolated anima."""

    path: str = Field(min_length=1, description="JSONL path relative to ANIMAWORKS_DATA_DIR")
    id_field: str = Field(min_length=1, description="Record field used as the stable lookup identifier")
    sensitive_fields: list[str] = Field(default_factory=list)
    searchable_fields: list[str] = Field(default_factory=list)

    @field_validator("path", "id_field")
    @classmethod
    def _require_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class EnclaveConfig(BaseModel):
    """Server-side configuration for an isolated (enclave) runtime instance.

    When ``enabled`` is ``True`` the server enforces a set of startup guards
    (see :mod:`core.enclave.guards`) and refuses to boot on violations.
    """

    enabled: bool = False
    name: str = ""
    socket_path: str = ""
    socket_group: str = ""
    entry_anima: str = ""
    allowed_peer_uids: list[int] = Field(default_factory=list)
    max_concurrency: int = 2
    request_timeout_s: int = 900
    allowed_llm_credentials: list[str] = Field(default_factory=list)
    datasets: dict[str, EnclaveDatasetConfig] = Field(default_factory=dict)
    egress: dict[str, Any] = Field(default_factory=dict)


class EnclaveClientConfig(BaseModel):
    """Client-side configuration for connecting to an enclave instance."""

    socket_path: str
    allowed_animas: list[str] = Field(default_factory=list)
    timeout_s: int = 900
