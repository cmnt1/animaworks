from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CLI command: ``animaworks cost`` — token usage and cost estimation."""

import argparse
import json
import sys
from pathlib import Path

from core.i18n import t

_BUDGET_FIELDS = ("month", "budget", "consumed", "remaining", "exceeded")


def cmd_cost(args: argparse.Namespace) -> None:
    """Show token usage and estimated cost."""
    from core.paths import get_data_dir
    from core.usage.token_budget import read_budget_fields
    from core.usage.token_usage import TokenUsageLogger

    data_dir = get_data_dir()
    animas_dir = data_dir / "animas"

    days = 1 if args.today else args.days

    if args.anima:
        anima_dir = animas_dir / args.anima
        if not anima_dir.is_dir():
            _cmd_single_enclave(args.anima, anima_dir, days, args.json_output)
            return
        _show_anima_cost(args.anima, anima_dir, days, args.json_output)
    else:
        anima_dirs = sorted(p for p in animas_dir.iterdir() if p.is_dir() and _has_usage_or_budget(p))
        enclave_usage, _ = _collect_enclave_usage(days)

        if not anima_dirs and not enclave_usage:
            print("No token usage data found. Start the server and send some messages.")
            return

        if args.json_output:
            result: dict = {}
            for ad in anima_dirs:
                logger = TokenUsageLogger(ad)
                summary = logger.summarize(days)
                summary.update(read_budget_fields(ad))
                result[ad.name] = summary
            for enclave, name, summary, _budget in enclave_usage:
                result[f"{name}@{enclave}"] = summary
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            grand_total_cost = 0.0
            grand_total_input = 0
            grand_total_output = 0
            grand_total_cache_read = 0
            grand_total_cache_write = 0
            grand_total_sessions = 0
            grand_total_unknown = 0

            for ad in anima_dirs:
                logger = TokenUsageLogger(ad)
                summary = logger.summarize(days)
                budget_fields = read_budget_fields(ad)
                if summary["total_sessions"] == 0 and budget_fields["budget"] is None:
                    continue
                grand_total_cost += summary["total_estimated_cost_usd"]
                grand_total_input += summary["total_input_tokens"]
                grand_total_output += summary["total_output_tokens"]
                grand_total_cache_read += summary.get("total_cache_read_tokens", 0)
                grand_total_cache_write += summary.get("total_cache_write_tokens", 0)
                grand_total_sessions += summary["total_sessions"]
                grand_total_unknown += summary.get("unknown_pricing_sessions", 0)
                _print_anima_summary(ad.name, summary, budget_fields)

            for enclave, name, summary, budget_fields in enclave_usage:
                if summary["total_sessions"] == 0 and budget_fields["budget"] is None:
                    continue
                grand_total_cost += summary["total_estimated_cost_usd"]
                grand_total_input += summary["total_input_tokens"]
                grand_total_output += summary["total_output_tokens"]
                grand_total_cache_read += summary.get("total_cache_read_tokens", 0)
                grand_total_cache_write += summary.get("total_cache_write_tokens", 0)
                grand_total_sessions += summary["total_sessions"]
                grand_total_unknown += summary.get("unknown_pricing_sessions", 0)
                _print_anima_summary(f"{name} (enclave: {enclave})", summary, budget_fields)

            if grand_total_sessions > 0:
                print("=" * 60)
                print(
                    f"{'TOTAL':>20s}  {grand_total_sessions:>6d} sessions  "
                    f"in:{_fmt_tokens(grand_total_input):>10s}  "
                    f"CacheR:{_fmt_tokens(grand_total_cache_read):>10s}  "
                    f"CacheW:{_fmt_tokens(grand_total_cache_write):>10s}  "
                    f"out:{_fmt_tokens(grand_total_output):>10s}  "
                    f"{_fmt_cost(grand_total_cost, grand_total_unknown, grand_total_sessions)}"
                )
                print()


def _bucket_summary(summary: dict) -> dict:
    """Return budget fields extracted from an enclave usage summary."""
    return {k: summary.get(k) for k in _BUDGET_FIELDS}


def _collect_enclave_usage(days: int) -> tuple[list, bool]:
    """Collect usage from every reachable enclave.

    Returns ``(results, any_reachable)`` where each result is a tuple of
    ``(enclave, anima, summary, budget_fields)``.  Unreachable enclaves
    print a single-line notice to stderr and are skipped.
    """
    from core.config import load_config
    from core.integrations.enclave import EnclavePermissionError, EnclaveUnreachable, fetch_enclave_usage

    config = load_config()
    results: list = []
    any_reachable = False
    for enclave_name, client_cfg in config.enclaves.items():
        try:
            data = fetch_enclave_usage(enclave_name, client_cfg, days)
        except EnclavePermissionError:
            print(
                f"Note: enclave '{enclave_name}' socket is not readable from this shell; skipping. "
                'Run with sg animaworks-enclave -c "animaworks cost" or log in again.',
                file=sys.stderr,
            )
            continue
        except EnclaveUnreachable:
            print(f"Note: enclave '{enclave_name}' is unreachable; skipping.", file=sys.stderr)
            continue
        any_reachable = True
        if data is None:
            continue
        for name, summary in data.get("animas", {}).items():
            results.append((enclave_name, name, summary, _bucket_summary(summary)))
    return results, any_reachable


def _cmd_single_enclave(name: str, anima_dir: Path, days: int, json_output: bool) -> None:
    """Show cost for an anima found on an enclave, else fail with exit 1."""
    from core.config import load_config
    from core.integrations.enclave import (
        EnclavePermissionError,
        EnclaveUnreachable,
        fetch_enclave_usage,
    )

    config = load_config()
    permission_error = False
    for enclave_name, client_cfg in config.enclaves.items():
        try:
            data = fetch_enclave_usage(enclave_name, client_cfg, days, anima=name)
        except EnclavePermissionError:
            permission_error = True
            continue
        except EnclaveUnreachable:
            continue
        if data is None:
            continue
        summary = data.get("animas", {}).get(name)
        if summary is None:
            continue
        budget_fields = _bucket_summary(summary)
        _display_anima_cost(f"{name} (enclave: {enclave_name})", summary, budget_fields, json_output, days)
        return

    if permission_error:
        print(
            f"Error: cannot read '{name}' from enclaves because the animaworks-enclave group "
            f"is not in the current shell. Run it as "
            f'sg animaworks-enclave -c "animaworks cost {name}" or log in again.'
        )
        sys.exit(1)

    print(f"Error: Anima '{name}' not found at {anima_dir}")
    sys.exit(1)


def _show_anima_cost(name: str, anima_dir: Path, days: int, json_output: bool) -> None:
    from core.usage.token_budget import read_budget_fields
    from core.usage.token_usage import TokenUsageLogger

    logger = TokenUsageLogger(anima_dir)
    summary = logger.summarize(days)
    budget_fields = read_budget_fields(anima_dir)
    _display_anima_cost(name, summary, budget_fields, json_output, days)


def _display_anima_cost(
    name: str,
    summary: dict,
    budget_fields: dict,
    json_output: bool,
    days: int,
) -> None:
    """Render one anima's usage summary (shared by local and enclave paths)."""

    if json_output:
        payload = dict(summary)
        payload.update(budget_fields)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if summary["total_sessions"] == 0:
        print(f"No token usage data for '{name}' in the last {days} day(s).")
        _print_budget_summary(budget_fields)
        return

    _print_anima_summary(name, summary, budget_fields)

    by_model = summary.get("by_model", {})
    if by_model:
        print(
            f"  {'Model':<35s} {'Sessions':>8s} {'Input':>10s} {'CacheR':>10s} {'CacheW':>10s} "
            f"{'Output':>10s} {'Cost':>10s}"
        )
        print(f"  {'-' * 35} {'-' * 8} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 10}")
        for model, data in sorted(by_model.items()):
            print(
                f"  {model:<35s} {data['sessions']:>8d} "
                f"{_fmt_tokens(data.get('input_tokens', 0)):>10s} "
                f"{_fmt_tokens(data.get('cache_read_tokens', 0)):>10s} "
                f"{_fmt_tokens(data.get('cache_write_tokens', 0)):>10s} "
                f"{_fmt_tokens(data.get('output_tokens', 0)):>10s} "
                f"{_fmt_cost(data['cost_usd'], data.get('unknown_pricing_sessions', 0), data['sessions'])}"
            )
        print()

    by_trigger = summary.get("by_trigger", {})
    if by_trigger:
        print(
            f"  {'Trigger':<20s} {'Sessions':>8s} {'Input':>10s} {'CacheR':>10s} {'CacheW':>10s} "
            f"{'Output':>10s} {'Cost':>10s}"
        )
        print(f"  {'-' * 20} {'-' * 8} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 10}")
        for trigger, data in sorted(by_trigger.items()):
            print(
                f"  {trigger:<20s} {data['sessions']:>8d} "
                f"{_fmt_tokens(data.get('input_tokens', 0)):>10s} "
                f"{_fmt_tokens(data.get('cache_read_tokens', 0)):>10s} "
                f"{_fmt_tokens(data.get('cache_write_tokens', 0)):>10s} "
                f"{_fmt_tokens(data.get('output_tokens', 0)):>10s} "
                f"{_fmt_cost(data['cost_usd'], data.get('unknown_pricing_sessions', 0), data['sessions'])}"
            )
        print()

    by_date = summary.get("by_date", {})
    if by_date:
        print(
            f"  {'Date':<12s} {'Sessions':>8s} {'Input':>10s} {'CacheR':>10s} {'CacheW':>10s} "
            f"{'Output':>10s} {'Cost':>10s}"
        )
        print(f"  {'-' * 12} {'-' * 8} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 10}")
        for day, data in sorted(by_date.items()):
            print(
                f"  {day:<12s} {data['sessions']:>8d} "
                f"{_fmt_tokens(data.get('input_tokens', 0)):>10s} "
                f"{_fmt_tokens(data.get('cache_read_tokens', 0)):>10s} "
                f"{_fmt_tokens(data.get('cache_write_tokens', 0)):>10s} "
                f"{_fmt_tokens(data.get('output_tokens', 0)):>10s} "
                f"{_fmt_cost(data['cost_usd'], data.get('unknown_pricing_sessions', 0), data['sessions'])}"
            )
        print()


def _has_usage_or_budget(anima_dir: Path) -> bool:
    """Keep legacy usage rows while including configured zero-usage budgets."""
    if (anima_dir / "token_usage").is_dir():
        return True
    try:
        from core.config.model_config import load_model_config

        return load_model_config(anima_dir).token_budget_monthly is not None
    except Exception:
        return False


def _print_budget_summary(budget_fields: dict[str, object]) -> None:
    budget = budget_fields["budget"]
    remaining = budget_fields["remaining"]
    budget_text = "-" if budget is None else _fmt_tokens(int(budget))
    remaining_text = "-" if remaining is None else _fmt_tokens(int(remaining))
    exceeded_text = "yes" if budget_fields["exceeded"] else "no"
    print(
        f"  Monthly budget: {budget_text}   "
        f"Consumed: {_fmt_tokens(int(budget_fields['consumed']))}   "
        f"Remaining: {remaining_text}   Exceeded: {exceeded_text}"
    )


def _print_anima_summary(name: str, summary: dict, budget_fields: dict[str, object]) -> None:
    print(f"\n  {name}")
    print(f"  {'─' * 56}")
    cache_r = summary.get("total_cache_read_tokens", 0)
    cache_w = summary.get("total_cache_write_tokens", 0)
    print(
        f"  Sessions: {summary['total_sessions']:,d}   "
        f"Input: {_fmt_tokens(summary['total_input_tokens'])}   "
        f"CacheR: {_fmt_tokens(cache_r)}   "
        f"CacheW: {_fmt_tokens(cache_w)}   "
        f"Output: {_fmt_tokens(summary['total_output_tokens'])}"
    )
    cost_text = _fmt_cost(
        summary["total_estimated_cost_usd"], summary.get("unknown_pricing_sessions", 0), summary["total_sessions"]
    )
    print(f"  Estimated cost: {cost_text}")
    _print_budget_summary(budget_fields)


def _fmt_cost(cost: float, unknown: int, sessions: int) -> str:
    if unknown and unknown >= sessions:
        return t("cost.unknown_pricing", count=unknown)
    if unknown:
        return t("cost.partial_pricing", cost=f"${cost:.4f}", count=unknown)
    return f"${cost:.4f}"


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)
