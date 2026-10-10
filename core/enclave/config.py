# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Configuration models for enclave mode."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class EnclaveDatasetConfig(BaseModel):
    """A JSONL dataset available to an isolated anima."""

    path: str = Field(min_length=1, description="JSONL path relative to ANIMAWORKS_DATA_DIR")
    id_field: str = Field(min_length=1, description="Record field used as the stable lookup identifier")
    searchable_fields: list[str] = Field(default_factory=list)

    @field_validator("path", "id_field")
    @classmethod
    def _require_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class EnclaveSsmTunnelConfig(BaseModel):
    """An SSM Session Manager port-forwarding tunnel to a remote host.

    Credentials come from the secrets store (``aws_secret``), never from
    environment variables or the boto profile chain.  Connection is made to
    a target resolved either by instance id or by EC2 ``Name`` tag (running
    instances only).
    """

    type: Literal["ssm_port_forward"] = "ssm_port_forward"
    region: str = Field(min_length=1, description="AWS region for SSM and target resolution")
    target_instance_id: str | None = None
    target_tag_name: str | None = None
    aws_secret: str = Field(min_length=1, description="Secret name holding AWS credential JSON")
    plugin_path: str = "/usr/local/bin/session-manager-plugin"
    idle_shutdown_s: int = 600

    @model_validator(mode="after")
    def _require_target(self) -> EnclaveSsmTunnelConfig:
        if bool(self.target_instance_id) == bool(self.target_tag_name):
            raise ValueError("exactly one of target_instance_id or target_tag_name is required")
        return self


class EnclaveAwsSourceConfig(BaseModel):
    """Allow-listed AWS read-only services available inside an enclave."""

    region: str = Field(min_length=1)
    aws_secret: str = Field(min_length=1, description="Secret name holding AWS credential JSON")
    log_groups: list[str] = Field(default_factory=list)
    pi_resource_id: str | None = None
    rds_instance_id: str | None = None
    s3_buckets: list[str] = Field(default_factory=list)
    max_bytes: int = 200_000

    @field_validator("region", "aws_secret")
    @classmethod
    def _require_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("max_bytes")
    @classmethod
    def _require_positive_max_bytes(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_bytes must be at least 1")
        return value


class EnclaveSqlSourceConfig(BaseModel):
    """A read-only SQL data source reachable from inside the enclave.

    The connection may go straight to ``host`` or through the optional
    ``tunnel`` (SSM port forward).  The database password is read from the
    secrets store by name (``password_secret``); it is never stored or
    logged in plaintext.
    """

    driver: Literal["mysql"] = "mysql"
    host: str = Field(min_length=1, description="Tunnel target (or direct) host")
    port: int = 3306
    database: str = Field(min_length=1)
    user: str = Field(min_length=1)
    password_secret: str = Field(min_length=1)
    ssl: bool = True
    ssl_ca: str | None = Field(default=None, description="Optional CA bundle path for TLS verification")
    ssl_verify_identity: bool = False
    tunnel: EnclaveSsmTunnelConfig | None = None
    max_rows: int = 200
    timeout_s: int = 30
    cell_max_chars: int = 2000
    app_key_secret: str | None = None
    decrypt_columns: list[str] = Field(default_factory=list)

    @field_validator("host", "database", "user", "password_secret")
    @classmethod
    def _require_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("max_rows")
    @classmethod
    def _clamp_max_rows(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_rows must be at least 1")
        return min(value, 1000)


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
    sql_sources: dict[str, EnclaveSqlSourceConfig] = Field(default_factory=dict)
    aws_sources: dict[str, EnclaveAwsSourceConfig] = Field(default_factory=dict)
    secrets_dir: str | None = None
    raw_dir: str = "raw"
    egress: dict[str, Any] = Field(default_factory=dict)


class EnclaveClientConfig(BaseModel):
    """Client-side configuration for connecting to an enclave instance."""

    socket_path: str
    allowed_animas: list[str] = Field(default_factory=list)
    timeout_s: int = 900
