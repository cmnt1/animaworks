# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Read secrets from the enclave credentials store.

Secrets are injected by systemd via ``LoadCredential=`` and exposed to the
process as files under ``$CREDENTIALS_DIRECTORY``.  They may also be placed
in a configured ``enclave.secrets_dir``.  Values are returned without the
trailing newline and are never emitted in logs or exception messages.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_SECRET_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class EnclaveSecretError(ValueError):
    """Raised when an enclave secret cannot be read (without leaking the value)."""


class _SecretMissingConfigError(EnclaveSecretError):
    """Raised when no secrets directory is configured or the enclave is disabled."""


def _enabled() -> bool:
    from core.config import load_config

    return load_config().enclave.enabled is True


def _secrets_dir() -> Path | None:
    """Return the secrets directory or ``None`` when none is configured."""
    credentials_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if credentials_dir:
        return Path(credentials_dir)

    from core.config import load_config

    configured = load_config().enclave.secrets_dir
    if configured:
        return Path(configured)
    return None


def _validate_name(name: str) -> str:
    """Return the validated secret name or raise without revealing the value."""
    if not isinstance(name, str) or not _SECRET_NAME_RE.match(name):
        raise EnclaveSecretError("invalid enclave secret name")
    return name


def read_enclave_secret(name: str) -> str:
    """Read a secret value by name, stripping any trailing newline.

    Raises :class:`EnclaveSecretError` when the enclave is disabled, no
    secrets directory is configured, the name is invalid, or the file is
    missing.  The value itself never appears in logs or exception text.
    """
    _validate_name(name)
    if not _enabled():
        raise _SecretMissingConfigError("enclave secret store is unavailable (enclave is disabled)")
    secrets_dir = _secrets_dir()
    if secrets_dir is None:
        raise _SecretMissingConfigError("no enclave secrets directory is configured")

    path = secrets_dir / name
    try:
        with path.open(encoding="utf-8") as stream:
            value = stream.read()
    except OSError as exc:
        logger.debug("Could not read enclave secret %s (%s)", name, type(exc).__name__)
        raise EnclaveSecretError("enclave secret is not available") from exc
    return value.rstrip("\r\n")


def secret_exists(name: str) -> bool:
    """Return whether a secret file exists, without reading its contents.

    Used by the doctor to report on secret provisioning.  ``False`` when the
    enclave is disabled, the name is invalid, or no directory is set.
    """
    if not isinstance(name, str) or not _SECRET_NAME_RE.match(name):
        return False
    if not _enabled():
        return False
    secrets_dir = _secrets_dir()
    if secrets_dir is None:
        return False
    return (secrets_dir / name).is_file()


__all__ = ["EnclaveSecretError", "read_enclave_secret", "secret_exists"]
