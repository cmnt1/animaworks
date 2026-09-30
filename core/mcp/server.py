from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Stdio MCP server exposing AnimaWorks tools for MCP-backed modes.

Used by Modes S/C/D/G/X and launched as ``python -m core.mcp.server``. Receives configuration via
environment variables:

- ``ANIMAWORKS_ANIMA_DIR`` -- path to the running anima's data directory
- ``ANIMAWORKS_PROJECT_DIR`` -- path to the AnimaWorks project root

The server name is ``aw`` so tools appear as ``mcp__aw__send_message`` etc.
in the corresponding execution engine's tool namespace.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from core.execution.session_context import RuntimeSessionContext, runtime_session_scope
from core.tooling.handler_base import active_session_type
from core.tooling.surface import (
    CONSOLIDATION_BLOCKED_TOOL_NAMES,
    MCP_TOOL_NAMES,
    SKILL_MANAGEMENT_TOOL_NAMES,
    ToolSurfaceContext,
    is_consolidation_trigger,
    is_full_tool_trigger,
    resolve_tool_surface,
)

# ── Logging (stderr only — stdout is MCP JSON-RPC) ──────
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ── MCP server instance ─────────────────────────────────
server = Server("aw")

# ── Tool selection ───────────────────────────────────────
# MCP schemas and runtime visibility are resolved by core.tooling.surface.


def _trigger_scoped_tools_enabled() -> bool:
    """Return whether trigger-scoped tool exposure is enabled (default True).

    Reads ``mcp.trigger_scoped_tools`` from the runtime config; any load
    failure falls back to True (the historical default).
    """
    try:
        from core.config.models import load_config

        return bool(load_config().mcp.trigger_scoped_tools)
    except Exception:
        return True


# Cached original parameter schemas (before relaxation) for type coercion
_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {}


def _relax_integer_types(schema: dict[str, Any]) -> dict[str, Any]:
    """Accept string values for integer parameters in MCP inputSchema.

    LLMs sometimes serialize numbers as strings (e.g. ``"10"`` instead
    of ``10``).  The MCP SDK validates strictly against the inputSchema,
    so we widen ``"type": "integer"`` to ``["integer", "string"]`` to
    let the call through.  Actual coercion happens in ``_coerce_integers``.
    """
    import copy

    schema = copy.deepcopy(schema)
    for _name, prop in schema.get("properties", {}).items():
        if prop.get("type") == "integer":
            prop["type"] = ["integer", "string"]
    return schema


def _coerce_integers(
    arguments: dict[str, Any],
    tool_name: str,
) -> dict[str, Any]:
    """Coerce string-valued integer arguments to actual ints.

    Matches against the canonical schema to find integer fields,
    then converts any string values that look numeric.
    """
    schema = _TOOL_SCHEMAS.get(tool_name)
    if not schema:
        return arguments
    props = schema.get("properties", {})
    for key, prop in props.items():
        if prop.get("type") == "integer" and key in arguments:
            val = arguments[key]
            if isinstance(val, str):
                try:
                    arguments[key] = int(val)
                except (ValueError, TypeError):
                    pass
    return arguments


def _build_mcp_tools() -> tuple[list[Tool], frozenset[str]]:
    """Convert canonical AnimaWorks schemas to MCP Tool objects.

    Reads the canonical schema lists and filters them to the widest profile
    returned by ``resolve_tool_surface``. External integrations are handled by
    their dedicated CLI/tool routes rather than this AnimaWorks schema set.

    Returns:
        Tuple of (tool_list, exposed_name_set) where exposed_name_set
        is the set of internal tool names.
    """
    from core.tooling.schemas import (
        ADMIN_TOOLS,
        KNOWLEDGE_TOOLS,
        MEMORY_TOOLS,
        PROCEDURE_TOOLS,
        _background_task_tools,
        _channel_tools,
        _check_permissions_tools,
        _create_skill_schemas,
        _curator_skill_schemas,
        _notification_tools,
        _submit_tasks_tools,
        _supervisor_tools,
        _task_tools,
        _vault_tools,
    )
    from core.tooling.schemas.workspace import WORKSPACE_TOOLS

    all_schemas: list[dict[str, Any]] = [
        *MEMORY_TOOLS,
        *_channel_tools(),
        *WORKSPACE_TOOLS,
        *_task_tools(),
        *_notification_tools(),
        *PROCEDURE_TOOLS,
        *KNOWLEDGE_TOOLS,
        *_supervisor_tools(),
        *ADMIN_TOOLS,
        *_create_skill_schemas(),
        *_curator_skill_schemas(),
        *_submit_tasks_tools(),
        *_background_task_tools(),
        *_vault_tools(),
        *_check_permissions_tools(),
    ]

    # Materialize the widest MCP profile once. list_tools() resolves the
    # current trigger and Anima-specific gates from the same policy at runtime.
    exposed = set(
        resolve_tool_surface(
            ToolSurfaceContext(
                has_subordinates=True,
                has_newstaff_skill=True,
                include_notification_tools=True,
                trigger_scoped_tools=False,
            ),
            "heartbeat",
            "S",
        )
    )
    configured = os.environ.get("ANIMAWORKS_MCP_TOOLS")
    if configured is not None:
        requested = {name.strip() for name in configured.split(",") if name.strip()}
        exposed.intersection_update(requested)

    # Apply file-backed description overrides
    from core.tooling.schemas import apply_prompt_descriptions

    all_schemas = apply_prompt_descriptions(all_schemas)

    # Cache original schemas for type coercion lookup
    for schema in all_schemas:
        if schema["name"] in exposed:
            _TOOL_SCHEMAS[schema["name"]] = schema.get("parameters", {})

    tools: list[Tool] = []
    for schema in all_schemas:
        name = schema["name"]
        if name not in exposed:
            continue
        desc = schema.get("description", "")
        input_schema = schema.get("parameters", {"type": "object", "properties": {}})
        input_schema = _relax_integer_types(input_schema)
        tools.append(
            Tool(
                name=name,
                description=desc,
                inputSchema=input_schema,
            )
        )

    # Verify we found all expected internal tools
    found = {t.name for t in tools}
    missing = exposed - found
    if missing:
        logger.warning("MCP tool schemas missing for: %s", ", ".join(sorted(missing)))

    return tools, frozenset(exposed)


# Build once at import time.  DB descriptions are baked in at this point;
# WebUI edits to tool descriptions will not take effect until the MCP
# subprocess is restarted (i.e. the parent Anima process restarts).
MCP_TOOLS: list[Tool]
_EXPOSED_NAMES: frozenset[str]
MCP_TOOLS, _EXPOSED_NAMES = _build_mcp_tools()

# ── Lazy ToolHandler initialisation ──────────────────────

_tool_handler: Any = None  # core.tooling.handler.ToolHandler | None
_init_error: str | None = None
_is_supervisor: bool | None = None
_has_newstaff: bool | None = None


def _has_subordinates_for_anima() -> bool:
    """Check if this Anima has subordinates via config.json.

    Evaluated once at first call and cached. Falls back to False (safe side —
    hides supervisor tools when check fails).
    """
    global _is_supervisor
    if _is_supervisor is not None:
        return _is_supervisor

    try:
        anima_dir_env = os.environ.get("ANIMAWORKS_ANIMA_DIR", "")
        if not anima_dir_env:
            _is_supervisor = False
            return False
        anima_name = Path(anima_dir_env).name

        from core.paths import get_data_dir

        config_path = get_data_dir() / "config.json"
        if not config_path.is_file():
            _is_supervisor = False
            return False

        import json as _json

        config_data = _json.loads(config_path.read_text(encoding="utf-8"))
        animas = config_data.get("animas", {})

        for other_name, other_cfg in animas.items():
            if other_name == anima_name:
                continue
            if isinstance(other_cfg, dict) and other_cfg.get("supervisor") == anima_name:
                _is_supervisor = True
                return True

        _is_supervisor = False
        return False
    except Exception:
        logger.debug("Failed to check subordinate status, defaulting to False")
        _is_supervisor = False
        return False


def _has_newstaff_skill_for_anima() -> bool:
    """Check if this Anima has the newstaff skill (hire permission).

    Looks for ``ANIMAWORKS_ANIMA_DIR/skills/newstaff/SKILL.md`` or
    ``skills/newstaff.md``.

    Evaluated once at first call and cached. Falls back to False (safe side —
    hides create_anima when check fails).
    """
    global _has_newstaff
    if _has_newstaff is not None:
        return _has_newstaff

    try:
        anima_dir_env = os.environ.get("ANIMAWORKS_ANIMA_DIR", "")
        if not anima_dir_env:
            _has_newstaff = False
            return False
        from core.anima.skills_check import has_newstaff_skill

        _has_newstaff = has_newstaff_skill(Path(anima_dir_env))
        return _has_newstaff
    except Exception:
        logger.debug("Failed to check newstaff skill, defaulting to False")
        _has_newstaff = False
        return False


def _get_tool_handler() -> Any:
    """Return the singleton ToolHandler, initialising on first call.

    Lazy initialisation keeps MCP server startup fast.  If initialisation
    fails the error is cached so subsequent calls return immediately.
    """
    global _tool_handler, _init_error

    if _tool_handler is not None:
        return _tool_handler
    if _init_error is not None:
        return None

    try:
        anima_dir_env = os.environ.get("ANIMAWORKS_ANIMA_DIR", "")
        if not anima_dir_env:
            _init_error = "ANIMAWORKS_ANIMA_DIR environment variable is not set"
            logger.error(_init_error)
            return None

        anima_dir = Path(anima_dir_env).resolve()
        if not anima_dir.is_dir():
            _init_error = f"ANIMAWORKS_ANIMA_DIR does not exist: {anima_dir}"
            logger.error(_init_error)
            return None

        from core.tooling.standalone import build_standalone_tool_handler

        _tool_handler = build_standalone_tool_handler(anima_dir, for_mcp=True)
        return _tool_handler

    except Exception as exc:
        _init_error = f"ToolHandler initialisation failed: {exc}"
        logger.exception(_init_error)
        return None


# ── Trust boundary labeling ───────────────────────────────


def _wrap_result(tool_name: str, result: str) -> str:
    """Apply trust boundary tag to a successful tool result.

    Falls back to the raw *result* when ``wrap_tool_result`` is
    unavailable (should never happen in practice, but keeps the
    MCP server resilient).
    """
    try:
        from core.trust import wrap_tool_result

        return wrap_tool_result(tool_name, result)
    except Exception:
        return result


# ── Tool execution timeout ───────────────────────────────

# Overall timeout for a single MCP tool call.  Prevents a hung handler
# (e.g. search_memory blocked on a degraded vector worker) from stalling
# the entire anima cycle indefinitely.
_DEFAULT_TOOL_TIMEOUT_S = 600.0  # 10 minutes

# Per-tool overrides.  MCP 公開ツールのうち長時間のものだけをここで延長する。
_TOOL_TIMEOUT_OVERRIDES: dict[str, float] = {
    "search_memory": 120.0,
    "create_anima": 1800.0,
    "curate_skills": 1800.0,
}


def _mcp_tools_env_for_trigger(trigger: str, *, enabled: bool) -> str | None:
    """Return the resolved scoped tool names for the MCP subprocess, if needed."""
    if not enabled or is_full_tool_trigger(trigger):
        return None
    names = resolve_tool_surface(
        ToolSurfaceContext(
            has_subordinates=True,
            has_newstaff_skill=True,
            include_notification_tools=True,
            trigger_scoped_tools=True,
        ),
        trigger,
        "S",
    )
    return ",".join(sorted(names))


def _resolve_tool_timeout(name: str) -> float | None:
    """Resolve the overall timeout (seconds) for a tool call.

    Returns ``None`` to disable the timeout (escape hatch when the
    resolved value is ``<= 0``).  Environment variable
    ``ANIMAWORKS_MCP_TOOL_TIMEOUT_DEFAULT`` overrides the hard-coded
    default; parse failures fall back to the hard-coded value.
    """
    default = _DEFAULT_TOOL_TIMEOUT_S
    env_val = os.environ.get("ANIMAWORKS_MCP_TOOL_TIMEOUT_DEFAULT")
    if env_val is not None:
        try:
            default = float(env_val)
        except (ValueError, TypeError):
            pass
    timeout = _TOOL_TIMEOUT_OVERRIDES.get(name, default)
    if timeout <= 0:
        return None
    return timeout


# ── MCP handlers ─────────────────────────────────────────


def _tool_not_found_message(name: str) -> str:
    """Build a localized "not exposed" message for *name*.

    For skill-management tools (only advertised during heartbeat /
    consolidation) an extra sentence explains when they become available.
    """
    from core.i18n import t as _t

    if name in SKILL_MANAGEMENT_TOOL_NAMES:
        return _t("mcp.tool_not_exposed.skill_curation", tool=name)
    return _t("mcp.tool_not_exposed", tool=name)


# A consolidation run finishes well within this; an older marker was left by a
# process killed before its ``finally`` ran and must not hide comms tools forever.
_CONSOLIDATION_MARKER_MAX_AGE_S = 6 * 3600


def _is_consolidation_mode() -> bool:
    """Check whether this Anima is currently running memory consolidation.

    Reads a flag file written by ``run_consolidation()`` in the main process.
    Markers older than ``_CONSOLIDATION_MARKER_MAX_AGE_S`` are treated as stale.
    """
    anima_dir_env = os.environ.get("ANIMAWORKS_ANIMA_DIR", "")
    if not anima_dir_env:
        return False
    marker = Path(anima_dir_env) / "state" / ".consolidation_mode"
    try:
        age = time.time() - marker.stat().st_mtime
    except OSError:
        return False
    if age > _CONSOLIDATION_MARKER_MAX_AGE_S:
        logger.warning("Ignoring stale consolidation marker %s (age %.0fs)", marker, age)
        return False
    return True


def _has_notification_channels_for_anima() -> bool:
    """Return whether at least one human-notification channel is enabled."""
    try:
        from core.config.models import load_config

        return any(channel.enabled for channel in load_config().human_notification.channels)
    except Exception:
        logger.debug("Failed to check human notification configuration", exc_info=True)
        return False


def _mcp_surface_context() -> ToolSurfaceContext:
    """Resolve runtime-only inputs for the shared MCP tool-surface policy."""
    env_flag = os.environ.get("ANIMAWORKS_ENABLE_SUBMIT_TASKS", "").strip().lower()
    return ToolSurfaceContext(
        has_subordinates=_has_subordinates_for_anima(),
        has_newstaff_skill=_has_newstaff_skill_for_anima(),
        include_notification_tools=_has_notification_channels_for_anima(),
        trigger_scoped_tools=_trigger_scoped_tools_enabled(),
        consolidation_mode=_is_consolidation_mode(),
        force_submit_tasks=env_flag in {"1", "true", "yes", "on"},
    )


def _current_mcp_tool_names(
    context: ToolSurfaceContext | None = None,
    trigger: str | None = None,
) -> frozenset[str]:
    current_trigger = trigger if trigger is not None else (os.environ.get("ANIMAWORKS_TRIGGER", "") or "").strip()
    resolved = frozenset(resolve_tool_surface(context or _mcp_surface_context(), current_trigger, "S"))
    exposed_external_tools = _EXPOSED_NAMES - frozenset(MCP_TOOL_NAMES)
    return (resolved & _EXPOSED_NAMES) | exposed_external_tools


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return tool schemas selected by the shared visibility resolver."""
    visible_names = _current_mcp_tool_names()
    return [tool for tool in MCP_TOOLS if tool.name in visible_names]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    """Dispatch a tool call to ToolHandler.handle() in a thread.

    ToolHandler.handle() is synchronous and may perform blocking I/O
    (file reads, subprocess calls), so we run it via ``asyncio.to_thread``
    to keep the MCP event loop responsive.
    """
    trigger = (os.environ.get("ANIMAWORKS_TRIGGER", "") or "").strip()
    surface_context = _mcp_surface_context()
    visible_names = _current_mcp_tool_names(surface_context, trigger)

    # Defense-in-depth follows the same consolidation policy as list_tools().
    if name in CONSOLIDATION_BLOCKED_TOOL_NAMES and (
        surface_context.consolidation_mode or is_consolidation_trigger(trigger)
    ):
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "status": "error",
                        "error_type": "ToolBlocked",
                        "message": f"Tool '{name}' is not available during memory consolidation",
                    },
                    ensure_ascii=False,
                ),
            )
        ]

    if name == "submit_tasks" and name in _EXPOSED_NAMES and name not in visible_names:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "status": "error",
                        "error_type": "ToolBlocked",
                        "message": (
                            "Tool 'submit_tasks' is only available in explicit background task-authoring sessions"
                        ),
                    },
                    ensure_ascii=False,
                ),
            )
        ]

    if name == "create_anima" and name in _EXPOSED_NAMES and not surface_context.has_newstaff_skill:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "status": "error",
                        "error_type": "ToolBlocked",
                        "message": (
                            "Tool 'create_anima' requires the newstaff skill. This anima does not have newstaff skill."
                        ),
                    },
                    ensure_ascii=False,
                ),
            )
        ]

    # Defense-in-depth: reject tool names outside the resolved runtime surface.
    # The Agent SDK should only call tools from list_tools(), but
    # ToolHandler.handle() would fall through to external dispatch
    # for unrecognised names, so we gate here explicitly.
    if name not in visible_names:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "status": "error",
                        "error_type": "ToolNotFound",
                        "message": _tool_not_found_message(name),
                    },
                    ensure_ascii=False,
                ),
            )
        ]

    handler = _get_tool_handler()
    if handler is None:
        error_msg = _init_error or "ToolHandler is not available"
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {"status": "error", "error_type": "InitError", "message": error_msg},
                    ensure_ascii=False,
                ),
            )
        ]

    coerced_args = _coerce_integers(dict(arguments or {}), name)
    if name == "search_memory" and "project" not in coerced_args:
        project = os.environ.get("ANIMAWORKS_MCP_PROJECT")
        if project is not None:
            coerced_args["project"] = project
    timeout = _resolve_tool_timeout(name)

    try:
        ctx = RuntimeSessionContext.from_env()
        if ctx is not None:
            handler.bind_runtime_session(ctx)
            token = handler.set_active_session_type(ctx.session_type)
            try:
                with runtime_session_scope(ctx):
                    # wait_for cancels the awaitable but does not stop the
                    # worker thread; it continues in the background until it finishes.
                    coro = asyncio.to_thread(handler.handle, name, coerced_args)
                    if timeout is not None:
                        result = await asyncio.wait_for(coro, timeout=timeout)
                    else:
                        result = await coro
            finally:
                active_session_type.reset(token)
        else:
            # wait_for cancels the awaitable but does not stop the
            # worker thread; it continues in the background until it finishes.
            coro = asyncio.to_thread(handler.handle, name, coerced_args)
            if timeout is not None:
                result = await asyncio.wait_for(coro, timeout=timeout)
            else:
                result = await coro
        wrapped = _wrap_result(name, result)
        return [TextContent(type="text", text=wrapped)]
    except TimeoutError as exc:
        # asyncio.wait_for raises TimeoutError (alias of asyncio.TimeoutError
        # on 3.11+).  The worker thread is NOT cancelled — it keeps running.
        # When timeout is None (disabled), a raw TimeoutError/socket.timeout
        # from the handler must not hit %.0f formatting — fall back to UnhandledError.
        if timeout is None:
            logger.exception("Unhandled error calling tool '%s'", name)
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "status": "error",
                            "error_type": "UnhandledError",
                            "message": f"Tool execution failed: {name}: {exc}",
                        },
                        ensure_ascii=False,
                    ),
                )
            ]
        logger.warning("Tool call timed out: tool=%s timeout=%.0fs", name, timeout)
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "status": "error",
                        "error_type": "ToolTimeout",
                        "message": (
                            f"Tool '{name}' timed out after {timeout:.0f}s. "
                            "The underlying operation may still be running; "
                            "do not retry immediately. Proceed with other work "
                            "or use a narrower query."
                        ),
                    },
                    ensure_ascii=False,
                ),
            )
        ]
    except Exception as exc:
        logger.exception("Unhandled error calling tool '%s'", name)
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "status": "error",
                        "error_type": "UnhandledError",
                        "message": f"Tool execution failed: {name}: {exc}",
                    },
                    ensure_ascii=False,
                ),
            )
        ]


# ── Entry point ──────────────────────────────────────────


async def main() -> None:
    """Run the MCP stdio server."""
    # The parent task runner owns its IPC connection; this MCP process keeps
    # the server URLs and routes via the host proxy, which forwards phase3
    # requests to that owner.
    logger.info("AnimaWorks MCP server starting (name=aw)")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
