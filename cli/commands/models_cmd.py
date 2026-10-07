"""CLI commands for model information and management."""

from __future__ import annotations

import argparse
import json
import sys

# ── Mode label mapping ────────────────────────────────────
_MODE_LABELS: dict[str, str] = {
    "S": "S (SDK)",
    "C": "C (Codex)",
    "D": "D (Cursor Agent CLI)",
    "G": "G (Gemini CLI)",
    "X": "X (Grok Build CLI)",
    "A": "A (Autonomous)",
}


def _fmt_context(value: int | None) -> str:
    """Format context window as human-readable string."""
    if value is None:
        return "-"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    return f"{value // 1_000}K"


# ── models list ───────────────────────────────────────────


def cmd_models_list(args: argparse.Namespace) -> None:
    """List known models with execution mode and context window."""
    from core.config.models import (
        KNOWN_MODELS,
        load_config,
    )
    from core.prompt.context import resolve_context_window

    load_config()
    mode_filter: str | None = getattr(args, "mode", None)

    rows: list[dict[str, str]] = []
    for m in KNOWN_MODELS:
        mode = m["mode"]
        if mode_filter and mode.upper() != mode_filter.upper():
            continue
        name = m["name"]
        cw = resolve_context_window(name)
        rows.append(
            {
                "name": name,
                "mode": mode,
                "context": _fmt_context(cw),
                "note": m.get("note", ""),
            }
        )

    if getattr(args, "json_output", False):
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    if not rows:
        print("No models found.")
        return

    name_w = max(len(r["name"]) for r in rows)
    name_w = max(name_w, 5)
    hdr = f"{'Name':<{name_w}}  {'Mode':<16}  {'Context':<10}  Note"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        mode_label = _MODE_LABELS.get(r["mode"], r["mode"])
        print(f"{r['name']:<{name_w}}  {mode_label:<16}  {r['context']:<10}  {r['note']}")

    from core.config.models import _load_models_json

    mj = _load_models_json()
    print(f"\nKnown models: {len(rows)}")
    if mj:
        print(f"User overrides (models.json): {len(mj)} patterns")


# ── models info ───────────────────────────────────────────


def cmd_models_info(args: argparse.Namespace) -> None:
    """Show resolved execution mode and context window for a model."""
    from core.config.models import (
        KNOWN_MODELS,
        load_config,
        resolve_execution_mode,
    )
    from core.prompt.context import (
        resolve_context_threshold,
        resolve_context_window,
    )

    model_name: str = args.model
    config = load_config()

    mode = resolve_execution_mode(config, model_name)
    cw = resolve_context_window(model_name)
    source = _resolve_source(model_name)

    threshold = resolve_context_threshold(0.50, cw)

    known_entry = next((m for m in KNOWN_MODELS if m["name"] == model_name), None)
    note = known_entry["note"] if known_entry else ""

    print(f"Model:            {model_name}")
    print(f"Execution Mode:   {_MODE_LABELS.get(mode, mode)}")
    print(f"Context Window:   {cw:,} tokens ({_fmt_context(cw)})")
    print(f"Threshold:        {threshold:.2f}")
    print(f"Source:            {source}")
    if note:
        print(f"Note:             {note}")


def _resolve_source(model_name: str) -> str:
    """Determine which source resolved this model's mode."""
    from core.config.models import _match_models_json

    entry = _match_models_json(model_name)
    if entry is not None and entry.get("mode"):
        return "models.json"
    return "built-in defaults"


# ── models show ───────────────────────────────────────────


def cmd_models_helpers(args: argparse.Namespace) -> None:
    """Show the resolved model and credential names for every helper role."""
    from core.config.helper_models import HELPER_MODEL_ROLES, resolve_helper_model
    from core.config.models import load_config
    from core.i18n import t
    from core.paths import get_animas_dir

    config = load_config()
    anima_name = getattr(args, "anima", None)
    anima_dir = None
    if anima_name:
        anima_dir = get_animas_dir() / anima_name
        if not anima_dir.is_dir():
            print(t("models.helpers.anima_not_found", anima=anima_name), file=sys.stderr)
            raise SystemExit(1)

    rows: list[dict[str, object]] = []
    for role in HELPER_MODEL_ROLES:
        resolved = resolve_helper_model(role, anima_dir, config=config)
        rows.append(
            {
                "role": role,
                "model": resolved.model,
                "credential": resolved.credential,
                "fallbacks": [
                    {"model": fallback.model, "credential": fallback.credential} for fallback in resolved.fallbacks
                ],
                "allow_agent_sdk_fallback": resolved.allow_agent_sdk_fallback,
                "max_output_tokens": resolved.max_output_tokens,
                "source": resolved.source,
            }
        )

    if getattr(args, "json_output", False):
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    print(t("models.helpers.title"))
    if anima_name:
        print(t("models.helpers.anima", anima=anima_name))
    headers = [
        t("models.helpers.role"),
        t("models.helpers.model"),
        t("models.helpers.credential"),
        t("models.helpers.fallbacks"),
        t("models.helpers.source"),
    ]
    widths = [
        max(len(header), *(len(str(row[key])) for row in rows))
        for header, key in zip(headers, ("role", "model", "credential", "fallbacks", "source"), strict=True)
    ]
    print("  ".join(f"{header:<{width}}" for header, width in zip(headers, widths, strict=True)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        fallback_text = ", ".join(
            f"{fallback['model']} ({fallback['credential'] or t('models.helpers.unset')})"
            for fallback in row["fallbacks"]
        ) or t("models.helpers.none")
        values = (
            str(row["role"]),
            str(row["model"]),
            str(row["credential"] or t("models.helpers.unset")),
            fallback_text,
            str(row["source"]),
        )
        print("  ".join(f"{value:<{width}}" for value, width in zip(values, widths, strict=True)))
        if row["allow_agent_sdk_fallback"] or row["max_output_tokens"] is not None:
            details: list[str] = []
            if row["allow_agent_sdk_fallback"]:
                details.append(t("models.helpers.sdk_fallback"))
            if row["max_output_tokens"] is not None:
                details.append(f"{t('models.helpers.max_output_tokens')}: {row['max_output_tokens']}")
            print(f"  {'; '.join(details)}")


# ── models show ───────────────────────────────────────────


def cmd_models_show(args: argparse.Namespace) -> None:
    """Show current models.json contents."""
    from core.paths import get_data_dir

    models_path = get_data_dir() / "models.json"
    if not models_path.exists():
        print(f"models.json not found at {models_path}")
        sys.exit(1)

    try:
        data = json.loads(models_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error reading models.json: {exc}")
        sys.exit(1)

    if getattr(args, "json_output", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if not isinstance(data, dict) or not data:
        print("models.json is empty or invalid.")
        return

    pattern_w = max(len(k) for k in data)
    pattern_w = max(pattern_w, 7)
    hdr = f"{'Pattern':<{pattern_w}}  {'Mode':<6}  Context"
    print(f"File: {models_path}\n")
    print(hdr)
    print("-" * len(hdr))
    for pattern, entry in data.items():
        if not isinstance(entry, dict):
            continue
        mode = entry.get("mode", "-")
        cw = entry.get("context_window")
        print(f"{pattern:<{pattern_w}}  {mode:<6}  {_fmt_context(cw)}")

    print(f"\nTotal: {len(data)} patterns")


# ── Registration ──────────────────────────────────────────


def register_models_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the 'models' subcommand group."""
    p_models = subparsers.add_parser("models", help="Model information and catalog")
    models_sub = p_models.add_subparsers(dest="models_command")

    # models list
    p_list = models_sub.add_parser("list", help="List known models")
    from core.config.model_mode import CANONICAL_MODES

    p_list.add_argument(
        "--mode",
        default=None,
        choices=[*sorted(CANONICAL_MODES), *(mode.lower() for mode in sorted(CANONICAL_MODES))],
        help="Filter by execution mode",
    )
    p_list.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )
    p_list.set_defaults(func=cmd_models_list)

    # models info
    p_info = models_sub.add_parser(
        "info",
        help="Show resolved mode and context for a model",
    )
    p_info.add_argument("model", help="Model name (e.g. claude-sonnet-5-5)")
    p_info.set_defaults(func=cmd_models_info)

    # models helpers
    p_helpers = models_sub.add_parser("helpers", help="Show resolved helper models")
    p_helpers.add_argument("--anima", default=None, help="Resolve per-anima helper overrides for this Anima")
    p_helpers.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")
    p_helpers.set_defaults(func=cmd_models_helpers)

    # models show
    p_show = models_sub.add_parser(
        "show",
        help="Show current models.json contents",
    )
    p_show.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output raw JSON",
    )
    p_show.set_defaults(func=cmd_models_show)

    p_models.set_defaults(func=lambda _args: p_models.print_help())
