# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Collect completed enclave ask jobs and deliver them to host inboxes."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
from collections.abc import Collection, Mapping, MutableMapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from core.i18n import t
from core.integrations.enclave import format_facts
from core.messaging.messenger import Messenger

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT_S = 30.0
_GATEWAY_URL = "http://enclave"


def should_start_host_delivery(config: Any) -> bool:
    """Return whether the host-side result collector should run for *config*."""
    enclave_mode = bool(getattr(getattr(config, "enclave", None), "enabled", False))
    return not enclave_mode and bool(getattr(config, "enclaves", None))


def _gateway_client(client_config: Any) -> httpx.Client:
    transport = httpx.HTTPTransport(uds=client_config.socket_path)
    # EnclaveClientConfig.timeout_s remains for configuration compatibility;
    # it does not control job duration or gateway HTTP requests.
    return httpx.Client(transport=transport, timeout=_HTTP_TIMEOUT_S)


def _warn_once(
    warnings: MutableMapping[str, str],
    key: str,
    state: str,
    message: str,
    *args: Any,
) -> None:
    if warnings.get(key) == state:
        return
    logger.warning(message, *args)
    warnings[key] = state


def _clear_warning(warnings: MutableMapping[str, str], key: str) -> None:
    warnings.pop(key, None)


def _load_jobs(
    http: httpx.Client,
    *,
    enclave_name: str,
    params: dict[str, str],
    warnings: MutableMapping[str, str],
    warning_key: str,
) -> list[dict[str, Any]] | None:
    try:
        response = http.get(f"{_GATEWAY_URL}/v1/jobs", params=params)
    except Exception as exc:
        state = f"connection:{type(exc).__name__}"
        _warn_once(
            warnings,
            warning_key,
            state,
            t("enclave.delivery.gateway_warning", enclave=enclave_name, reason=state),
        )
        return None

    if response.status_code != 200:
        state = f"http:{response.status_code}"
        _warn_once(
            warnings,
            warning_key,
            state,
            t("enclave.delivery.gateway_warning", enclave=enclave_name, reason=state),
        )
        return None

    try:
        payload = response.json()
    except (ValueError, TypeError):
        payload = None
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        state = "invalid-json"
        _warn_once(
            warnings,
            warning_key,
            state,
            t("enclave.delivery.gateway_warning", enclave=enclave_name, reason=state),
        )
        return None
    jobs = payload["jobs"]
    if any(not isinstance(job, dict) for job in jobs):
        state = "invalid-job-list"
        _warn_once(
            warnings,
            warning_key,
            state,
            t("enclave.delivery.gateway_warning", enclave=enclave_name, reason=state),
        )
        return None

    _clear_warning(warnings, warning_key)
    return jobs


def _safe_sender_name(enclave_name: str) -> str:
    """Return a Messenger-compatible sender name for an enclave config name."""
    slug = re.sub(r"[^a-z0-9_-]+", "-", enclave_name.lower()).strip("-_") or "unknown"
    if len(slug) > 23:
        suffix = hashlib.sha256(enclave_name.encode("utf-8")).hexdigest()[:8]
        slug = f"{slug[:14].rstrip('-_')}-{suffix}"
    return f"enclave-{slug}"


def _delivery_id(enclave_name: str, job_id: str) -> str:
    digest = hashlib.sha256(f"{enclave_name}:{job_id}".encode()).hexdigest()
    return f"enclave-{digest}"


def _format_delivery(job: Mapping[str, Any]) -> str:
    lines = [
        t("enclave.delivery.case_id", case_id=str(job.get("case_id") or "")),
        t("enclave.delivery.job_id", job_id=str(job.get("job_id") or "")),
        t("enclave.delivery.status", status=str(job.get("status") or "unknown")),
    ]
    facts_lines = format_facts(job.get("facts"))
    lines.extend(facts_lines)
    if not facts_lines:
        lines.append(t("enclave.delivery.no_facts"))
    if job.get("audit_id"):
        lines.append(t("enclave.delivery.audit_id", audit_id=str(job["audit_id"])))
    if job.get("error"):
        lines.append(t("enclave.delivery.error", error=str(job["error"])))
    return "\n".join(lines)


def _ack_job(
    http: httpx.Client,
    *,
    enclave_name: str,
    job_id: str,
    warnings: MutableMapping[str, str],
) -> bool:
    warning_key = f"ack:{enclave_name}:{job_id}"
    url = f"{_GATEWAY_URL}/v1/ask/{quote(job_id, safe='')}/ack"
    try:
        response = http.post(url)
    except Exception as exc:
        state = f"connection:{type(exc).__name__}"
        _warn_once(
            warnings,
            warning_key,
            state,
            t("enclave.delivery.job_warning", enclave=enclave_name, job_id=job_id, reason=state),
        )
        return False
    if not response.is_success:
        _warn_once(
            warnings,
            warning_key,
            f"http:{response.status_code}",
            t("enclave.delivery.ack_warning", enclave=enclave_name, job_id=job_id, code=response.status_code),
        )
        return False
    _clear_warning(warnings, warning_key)
    return True


def deliver_undelivered_once(
    enclaves: Mapping[str, Any],
    anima_names: Collection[str],
    shared_dir: Path,
    *,
    warning_state: MutableMapping[str, str] | None = None,
    stop_event: threading.Event | None = None,
) -> int:
    """Deliver one batch of undelivered jobs; return the number delivered."""
    warnings = warning_state if warning_state is not None else {}
    known_animas = set(anima_names)
    delivered_count = 0

    for enclave_name, client_config in enclaves.items():
        if stop_event is not None and stop_event.is_set():
            break
        gateway_warning_key = f"gateway:{enclave_name}"
        try:
            with _gateway_client(client_config) as http:
                jobs = _load_jobs(
                    http,
                    enclave_name=enclave_name,
                    params={"undelivered": "1"},
                    warnings=warnings,
                    warning_key=gateway_warning_key,
                )
                if jobs is None:
                    continue

                allowed_animas = list(getattr(client_config, "allowed_animas", []) or [])
                for listed_job in jobs:
                    if stop_event is not None and stop_event.is_set():
                        break
                    job = dict(listed_job)
                    job_id = job.get("job_id")
                    if not isinstance(job_id, str) or not job_id:
                        _warn_once(
                            warnings,
                            f"invalid-job:{enclave_name}",
                            "missing-job-id",
                            "Ignoring an undelivered enclave job without a job_id from %s",
                            enclave_name,
                        )
                        continue

                    origin = job.get("from_anima")
                    if origin not in allowed_animas or origin not in known_animas:
                        _warn_once(
                            warnings,
                            f"invalid-origin:{enclave_name}:{job_id}",
                            str(origin),
                            t("enclave.delivery.invalid_sender", enclave=enclave_name, job_id=job_id),
                        )
                        if _ack_job(
                            http,
                            enclave_name=enclave_name,
                            job_id=job_id,
                            warnings=warnings,
                        ):
                            _clear_warning(warnings, f"invalid-origin:{enclave_name}:{job_id}")
                        continue

                    delivery_warning_key = f"delivery:{enclave_name}:{job_id}"
                    try:
                        messenger = Messenger(shared_dir, _safe_sender_name(enclave_name))
                        messenger.send(
                            to=origin,
                            content=_format_delivery(job),
                            intent="report",
                            source="human",
                            delivery_id=_delivery_id(enclave_name, job_id),
                        )
                    except Exception as exc:
                        state = type(exc).__name__
                        _warn_once(
                            warnings,
                            delivery_warning_key,
                            state,
                            t("enclave.delivery.job_warning", enclave=enclave_name, job_id=job_id, reason=state),
                        )
                        continue

                    if _ack_job(
                        http,
                        enclave_name=enclave_name,
                        job_id=job_id,
                        warnings=warnings,
                    ):
                        delivered_count += 1
                        _clear_warning(warnings, delivery_warning_key)
        except Exception as exc:
            state = f"client:{type(exc).__name__}"
            _warn_once(
                warnings,
                gateway_warning_key,
                state,
                t("enclave.delivery.gateway_warning", enclave=enclave_name, reason=state),
            )

    return delivered_count


async def host_delivery_loop(
    enclaves: Mapping[str, Any],
    anima_names: Collection[str],
    shared_dir: Path,
    *,
    stop_event: threading.Event,
    warning_state: MutableMapping[str, str] | None = None,
    interval_s: float = 60.0,
) -> None:
    """Poll enclave gateways immediately and then at a bounded interval."""
    warnings = warning_state if warning_state is not None else {}
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(
                deliver_undelivered_once,
                enclaves,
                anima_names,
                shared_dir,
                warning_state=warnings,
                stop_event=stop_event,
            )
            _clear_warning(warnings, "host-delivery-loop")
        except Exception as exc:
            state = type(exc).__name__
            _warn_once(
                warnings,
                "host-delivery-loop",
                state,
                "Enclave host delivery cycle failed (%s)",
                state,
            )
        if stop_event.is_set():
            return
        await asyncio.to_thread(stop_event.wait, max(0.0, interval_s))


__all__ = [
    "deliver_undelivered_once",
    "host_delivery_loop",
    "should_start_host_delivery",
]
