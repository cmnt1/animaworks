# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for Laravel-compatible encrypted string handling."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from core.enclave.laravel_crypt import decrypt_string, parse_app_keys


def _encrypt_string(plaintext: str, key: bytes) -> str:
    iv = bytes(range(16))
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    iv_text = base64.b64encode(iv).decode("ascii")
    value_text = base64.b64encode(ciphertext).decode("ascii")
    mac = hmac.new(key, (iv_text + value_text).encode("ascii"), hashlib.sha256).hexdigest()
    payload: dict[str, Any] = {"iv": iv_text, "value": value_text, "mac": mac, "tag": ""}
    serialized = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(serialized).decode("ascii")


def _decode_payload(payload: str) -> dict[str, Any]:
    decoded = base64.b64decode(payload, validate=True)
    return json.loads(decoded)


def _encode_payload(payload: dict[str, Any]) -> str:
    return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")


def test_decrypt_string_uses_laravel_aes_256_cbc_format() -> None:
    key = bytes(range(32))
    encrypted = _encrypt_string("dummy Laravel encrypted text", key)

    assert decrypt_string(encrypted, [key]) == "dummy Laravel encrypted text"


def test_decrypt_string_rejects_mac_tampering() -> None:
    key = bytes(range(32))
    payload = _decode_payload(_encrypt_string("dummy tamper target", key))
    payload["mac"] = ("0" if payload["mac"][0] != "0" else "1") + payload["mac"][1:]

    assert decrypt_string(_encode_payload(payload), [key]) is None


def test_decrypt_string_rejects_a_different_key() -> None:
    key = bytes(range(32))
    different_key = bytes(range(1, 33))

    assert decrypt_string(_encrypt_string("dummy wrong-key target", key), [different_key]) is None


def test_parse_app_keys_supports_base64_and_plain_utf8_keys() -> None:
    base64_key = bytes(range(32))
    plain_key = b"plain dummy key".ljust(32, b"!")
    raw = f"  base64:{base64.b64encode(base64_key).decode('ascii')}  \n\n  {plain_key.decode('utf-8')}  "

    assert parse_app_keys(raw) == [base64_key, plain_key]


def test_decrypt_string_tries_a_previous_key_from_the_second_line() -> None:
    current_key = bytes(range(32))
    previous_key = bytes(range(32, 64))
    raw_keys = "\n".join(
        [
            f"base64:{base64.b64encode(current_key).decode('ascii')}",
            f"base64:{base64.b64encode(previous_key).decode('ascii')}",
        ]
    )
    keys = parse_app_keys(raw_keys)

    assert decrypt_string(_encrypt_string("dummy legacy-key text", previous_key), keys) == "dummy legacy-key text"


def test_decrypt_string_rejects_nonempty_gcm_tag() -> None:
    key = bytes(range(32))
    payload = _decode_payload(_encrypt_string("dummy unsupported tag", key))
    payload["tag"] = "00"

    assert decrypt_string(_encode_payload(payload), [key]) is None
