# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for enclave secret loading (systemd LoadCredential / secrets_dir)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config import invalidate_cache
from core.enclave.secrets import EnclaveSecretError, read_enclave_secret, secret_exists
from tests.helpers.filesystem import DEFAULT_TEST_CONFIG


def _write_config(data_dir: Path, *, enabled: bool = True, secrets_dir: str | None = None) -> None:
    config: dict = dict(DEFAULT_TEST_CONFIG)
    config["enclave"] = {
        "enabled": enabled,
        "secrets_dir": secrets_dir,
    }
    (data_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    invalidate_cache()


def _write_secret(credentials_dir: Path, name: str, value: str) -> None:
    credentials_dir.mkdir(parents=True, exist_ok=True)
    (credentials_dir / name).write_text(value, encoding="utf-8")


def test_read_secret_from_credentials_directory(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    credentials_dir = data_dir / "secretstore"
    _write_secret(credentials_dir, "db-password", "the-secret\n")
    _write_config(data_dir, secrets_dir=str(credentials_dir))
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credentials_dir))

    assert read_enclave_secret("db-password") == "the-secret"


def test_read_secret_strips_multiple_trailing_newlines(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    credentials_dir = data_dir / "secretstore"
    _write_secret(credentials_dir, "db-password", "secret-value\r\n")
    _write_config(data_dir, secrets_dir=str(credentials_dir))
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credentials_dir))

    assert read_enclave_secret("db-password") == "secret-value"


def test_read_secret_from_configured_secrets_dir(data_dir: Path) -> None:
    credentials_dir = data_dir / "secretstore"
    _write_secret(credentials_dir, "cred", "val")
    _write_config(data_dir, secrets_dir=str(credentials_dir))

    assert read_enclave_secret("cred") == "val"


def test_missing_file_raises_without_value(data_dir: Path) -> None:
    credentials_dir = data_dir / "secretstore"
    _write_config(data_dir, secrets_dir=str(credentials_dir))

    with pytest.raises(EnclaveSecretError):
        read_enclave_secret("missing")
    # The value must not leak into the exception message.
    with pytest.raises(EnclaveSecretError) as exc_info:
        read_enclave_secret("missing")
    assert "missing" not in exc_info.value.args[0]


def test_no_directory_raises(data_dir: Path) -> None:
    _write_config(data_dir, secrets_dir=None)
    with pytest.raises(EnclaveSecretError):
        read_enclave_secret("db-password")


def test_disabled_enclave_raises(data_dir: Path) -> None:
    credentials_dir = data_dir / "secretstore"
    _write_secret(credentials_dir, "db-password", "val")
    _write_config(data_dir, enabled=False, secrets_dir=str(credentials_dir))
    with pytest.raises(EnclaveSecretError):
        read_enclave_secret("db-password")


@pytest.mark.parametrize(
    "name",
    ["", "a/b", "..", "../secret", "a b", "x" * 65, "a\nb"],
)
def test_invalid_names_are_rejected(data_dir: Path, name: str) -> None:
    _write_config(data_dir, secrets_dir=str(data_dir / "secretstore"))
    with pytest.raises(EnclaveSecretError):
        read_enclave_secret(name)


@pytest.mark.parametrize("name", ["db-password", "AWS_CREDS", "a.b-c_1", "x" * 64])
def test_valid_names_are_accepted(data_dir: Path, name: str) -> None:
    credentials_dir = data_dir / "secretstore"
    _write_secret(credentials_dir, name, "val")
    _write_config(data_dir, secrets_dir=str(credentials_dir))
    assert read_enclave_secret(name) == "val"


def test_secret_exists_does_not_read_content(data_dir: Path) -> None:
    credentials_dir = data_dir / "secretstore"
    _write_secret(credentials_dir, "present", "val")
    _write_config(data_dir, secrets_dir=str(credentials_dir))

    assert secret_exists("present") is True
    assert secret_exists("absent") is False
    assert secret_exists("a/b") is False


def test_secret_exists_false_when_disabled(data_dir: Path) -> None:
    credentials_dir = data_dir / "secretstore"
    _write_secret(credentials_dir, "present", "val")
    _write_config(data_dir, enabled=False, secrets_dir=str(credentials_dir))
    assert secret_exists("present") is False
