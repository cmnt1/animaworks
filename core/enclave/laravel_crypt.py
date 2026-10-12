# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Helpers for decrypting Laravel ``Crypt::encryptString`` payloads."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
from typing import Any


def parse_app_keys(raw: str) -> list[bytes]:
    """Parse newline-separated Laravel application keys.

    The first non-empty line is the current key and subsequent lines can hold
    previous keys for data encrypted before a key rotation. Invalid base64
    lines are ignored so they cannot prevent later keys from being tried.
    """
    if not isinstance(raw, str):
        return []

    keys: list[bytes] = []
    for line in raw.splitlines():
        value = line.strip()
        if not value:
            continue
        if value.startswith("base64:"):
            try:
                key = base64.b64decode(value.removeprefix("base64:"), validate=True)
            except (binascii.Error, ValueError):
                continue
            if key:
                keys.append(key)
            continue
        try:
            key = value.encode("utf-8")
        except UnicodeEncodeError:
            continue
        if key:
            keys.append(key)
    return keys


def decrypt_string(payload: str, keys: list[bytes]) -> str | None:
    """Authenticate and decrypt a Laravel AES-256-CBC string payload.

    Invalid payloads, unsupported cipher formats, authentication failures and
    invalid plaintext encodings all return ``None``. No details from malformed
    payloads or keys are exposed to callers.
    """
    if not isinstance(payload, str) or not isinstance(keys, list):
        return None

    try:
        decoded_payload = base64.b64decode(payload, validate=True)
        data: Any = json.loads(decoded_payload)
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    iv_text = data.get("iv")
    value_text = data.get("value")
    mac = data.get("mac")
    tag = data.get("tag")
    if not isinstance(iv_text, str) or not isinstance(value_text, str) or not isinstance(mac, str):
        return None
    if not isinstance(tag, str) or tag:
        return None
    if len(mac) != 64:
        return None

    try:
        iv = base64.b64decode(iv_text, validate=True)
        ciphertext = base64.b64decode(value_text, validate=True)
        mac_input = (iv_text + value_text).encode("ascii")
    except (binascii.Error, UnicodeEncodeError, ValueError):
        return None

    if len(iv) != 16 or not ciphertext or len(ciphertext) % 16:
        return None

    try:
        from cryptography.hazmat.primitives import hashes, padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.hmac import HMAC
    except ImportError:
        return None

    for key in keys:
        if not isinstance(key, bytes) or len(key) != 32:
            continue
        try:
            verifier = HMAC(key, hashes.SHA256())
            verifier.update(mac_input)
            expected_mac = verifier.finalize().hex()
            if not hmac.compare_digest(expected_mac, mac):
                continue

            decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
            padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
            plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
            return plaintext.decode("utf-8")
        except Exception:  # noqa: BLE001 - malformed ciphertext must never escape
            continue
    return None


__all__ = ["decrypt_string", "parse_app_keys"]
