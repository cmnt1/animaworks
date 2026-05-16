# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""AnimaWorks NotebookLM tool -- Google NotebookLM integration.

Provides notebook management, source ingestion, chat (Q&A against sources),
and artifact generation (audio overviews, reports, etc.) via notebooklm-py.
"""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

try:
    from notebooklm import (
        ArtifactType,
        AuthError,
        NotebookLMClient,
        NotebookLMError,
        ReportFormat,
    )
except ImportError:
    raise ImportError(
        "notebooklm tool requires notebooklm-py. Install with: pip install animaworks[notebooklm]"
    ) from None

logger = logging.getLogger(__name__)


def _get_source_type(source: Any) -> str:
    """v0.3.x: source.type / v0.4.x: source.kind の両方に対応するヘルパー。"""
    val = getattr(source, "kind", None) or getattr(source, "type", None)
    return str(val) if val is not None else "unknown"


# ── Execution Profile ─────────────────────────────────────

EXECUTION_PROFILE: dict[str, dict[str, object]] = {
    "list_notebooks": {"expected_seconds": 10, "background_eligible": False},
    "get_notebook": {"expected_seconds": 15, "background_eligible": False},
    "create_notebook": {"expected_seconds": 10, "background_eligible": False},
    "delete_notebook": {"expected_seconds": 10, "background_eligible": False},
    "get_source_fulltext": {"expected_seconds": 15, "background_eligible": False},
    "add_source_url": {"expected_seconds": 30, "background_eligible": False},
    "add_source_text": {"expected_seconds": 15, "background_eligible": False},
    "add_source_file": {"expected_seconds": 60, "background_eligible": True},
    "list_sources": {"expected_seconds": 10, "background_eligible": False},
    "chat": {"expected_seconds": 30, "background_eligible": False},
    "generate_artifact": {"expected_seconds": 300, "background_eligible": True},
    "list_artifacts": {"expected_seconds": 10, "background_eligible": False},
}

# ── Async bridge ──────────────────────────────────────────

_DEFAULT_STORAGE = Path.home() / ".notebooklm" / "storage_state.json"


def _resolve_storage_path() -> str:
    """Resolve the NotebookLM storage-state file path."""
    env = os.environ.get("NOTEBOOKLM_STORAGE_PATH")
    path = Path(env) if env else _DEFAULT_STORAGE
    if not path.exists():
        msg = f"NotebookLM requires authentication. Run 'notebooklm login' first. Expected: {path}"
        raise FileNotFoundError(msg)
    return str(path)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from a sync context."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside an event loop (e.g. FastAPI) — offload to a thread.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


# ── Async helpers ─────────────────────────────────────────


async def _list_notebooks() -> list[dict[str, Any]]:
    path = _resolve_storage_path()
    async with await NotebookLMClient.from_storage(path) as client:
        notebooks = await client.notebooks.list()
        return [{"id": nb.id, "title": nb.title} for nb in notebooks]


async def _create_notebook(title: str) -> dict[str, Any]:
    path = _resolve_storage_path()
    async with await NotebookLMClient.from_storage(path) as client:
        nb = await client.notebooks.create(title)
        return {"id": nb.id, "title": nb.title}


async def _delete_notebook(notebook_id: str) -> dict[str, Any]:
    path = _resolve_storage_path()
    async with await NotebookLMClient.from_storage(path) as client:
        await client.notebooks.delete(notebook_id)
        return {"success": True, "notebook_id": notebook_id}


async def _add_source_url(notebook_id: str, url: str) -> dict[str, Any]:
    path = _resolve_storage_path()
    async with await NotebookLMClient.from_storage(path) as client:
        source = await client.sources.add_url(notebook_id, url)
        return {"id": source.id, "title": source.title, "type": _get_source_type(source)}


async def _add_source_text(
    notebook_id: str,
    text: str,
    title: str | None = None,
) -> dict[str, Any]:
    path = _resolve_storage_path()
    async with await NotebookLMClient.from_storage(path) as client:
        source = await client.sources.add_text(notebook_id, text, title=title)
        return {"id": source.id, "title": source.title, "type": _get_source_type(source)}


async def _add_source_file(notebook_id: str, file_path: str) -> dict[str, Any]:
    path = _resolve_storage_path()
    async with await NotebookLMClient.from_storage(path) as client:
        source = await client.sources.add_file(notebook_id, file_path)
        return {"id": source.id, "title": source.title, "type": _get_source_type(source)}


async def _get_notebook(notebook_id: str) -> dict[str, Any]:
    path = _resolve_storage_path()
    async with await NotebookLMClient.from_storage(path) as client:
        desc = await client.notebooks.get_description(notebook_id)
        topics = []
        for t in desc.suggested_topics or []:
            topics.append(t.question if hasattr(t, "question") else str(t))
        return {
            "id": notebook_id,
            "summary": desc.summary,
            "suggested_topics": topics,
        }


async def _get_source_fulltext(notebook_id: str, source_id: str) -> dict[str, Any]:
    path = _resolve_storage_path()
    async with await NotebookLMClient.from_storage(path) as client:
        ft = await client.sources.get_fulltext(notebook_id, source_id)
        return {
            "source_id": source_id,
            "title": ft.title,
            "content": ft.content,
        }


async def _list_sources(notebook_id: str) -> list[dict[str, Any]]:
    path = _resolve_storage_path()
    async with await NotebookLMClient.from_storage(path) as client:
        sources = await client.sources.list(notebook_id)
        return [{"id": s.id, "title": s.title, "type": _get_source_type(s)} for s in sources]


async def _chat(notebook_id: str, message: str) -> dict[str, Any]:
    path = _resolve_storage_path()
    async with await NotebookLMClient.from_storage(path) as client:
        result = await client.chat.ask(notebook_id, message)
        return {
            "answer": result.answer,
            "references": [{"source_id": ref.source_id, "text": ref.text} for ref in (result.references or [])],
        }


# ── Artifact type mapping ────────────────────────────────

_ARTIFACT_TYPE_MAP: dict[str, str] = {
    "audio_overview": "audio",
    "briefing_doc": "report",
    "study_guide": "report",
    "faq": "report",
    "timeline": "report",
    "mind_map": "mind_map",
}

_REPORT_FORMAT_MAP: dict[str, ReportFormat] = {
    "briefing_doc": ReportFormat.BRIEFING_DOC,
    "study_guide": ReportFormat.STUDY_GUIDE,
}


async def _generate_artifact(
    notebook_id: str,
    artifact_type: str,
    language: str = "en",
    instructions: str | None = None,
) -> dict[str, Any]:
    path = _resolve_storage_path()
    category = _ARTIFACT_TYPE_MAP.get(artifact_type)
    if category is None:
        valid = ", ".join(sorted(_ARTIFACT_TYPE_MAP))
        return {"success": False, "error": f"Unknown artifact_type '{artifact_type}'. Valid: {valid}"}

    async with await NotebookLMClient.from_storage(path) as client:
        if category == "audio":
            status = await client.artifacts.generate_audio(
                notebook_id,
                language=language,
                instructions=instructions,
            )
        elif category == "mind_map":
            status = await client.artifacts.generate_mind_map(
                notebook_id,
                language=language,
            )
        else:
            report_fmt = _REPORT_FORMAT_MAP.get(artifact_type, ReportFormat.BRIEFING_DOC)
            status = await client.artifacts.generate_report(
                notebook_id,
                report_format=report_fmt,
                language=language,
                custom_prompt=instructions,
            )
        return {
            "success": True,
            "task_id": status.task_id if hasattr(status, "task_id") else None,
            "artifact_type": artifact_type,
        }


async def _list_artifacts(
    notebook_id: str,
    artifact_type: str | None = None,
) -> list[dict[str, Any]]:
    path = _resolve_storage_path()
    async with await NotebookLMClient.from_storage(path) as client:
        at = None
        if artifact_type:
            try:
                at = ArtifactType(artifact_type.upper())
            except (ValueError, KeyError):
                pass
        artifacts = await client.artifacts.list(notebook_id, artifact_type=at)
        return [
            {
                "id": a.id,
                "title": a.title,
                "kind": str(a.kind) if hasattr(a, "kind") else None,
            }
            for a in artifacts
        ]


# ── Tool schemas ──────────────────────────────────────────


def get_tool_schemas() -> list[dict]:
    """Return Anthropic tool_use schemas for NotebookLM tools."""
    return [
        {
            "name": "notebooklm_list_notebooks",
            "description": "List all Google NotebookLM notebooks.",
            "input_schema": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "notebooklm_get_notebook",
            "description": "Get a NotebookLM notebook's summary, description, and topics.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "notebook_id": {"type": "string", "description": "Notebook ID"},
                },
                "required": ["notebook_id"],
            },
        },
        {
            "name": "notebooklm_create_notebook",
            "description": "Create a new Google NotebookLM notebook.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Notebook title"},
                },
                "required": ["title"],
            },
        },
        {
            "name": "notebooklm_delete_notebook",
            "description": "Delete a Google NotebookLM notebook.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "notebook_id": {"type": "string", "description": "Notebook ID"},
                },
                "required": ["notebook_id"],
            },
        },
        {
            "name": "notebooklm_add_source_url",
            "description": "Add a web page URL as a source to a NotebookLM notebook.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "notebook_id": {"type": "string", "description": "Notebook ID"},
                    "url": {"type": "string", "description": "Web page URL to add"},
                },
                "required": ["notebook_id", "url"],
            },
        },
        {
            "name": "notebooklm_add_source_text",
            "description": "Add pasted text as a source to a NotebookLM notebook.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "notebook_id": {"type": "string", "description": "Notebook ID"},
                    "text": {"type": "string", "description": "Text content to add"},
                    "title": {"type": "string", "description": "Optional title for the source"},
                },
                "required": ["notebook_id", "text"],
            },
        },
        {
            "name": "notebooklm_add_source_file",
            "description": "Add a local file (PDF, DOCX, MD, CSV, etc.) as a source to a NotebookLM notebook.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "notebook_id": {"type": "string", "description": "Notebook ID"},
                    "file_path": {"type": "string", "description": "Absolute path to the file"},
                },
                "required": ["notebook_id", "file_path"],
            },
        },
        {
            "name": "notebooklm_get_source_fulltext",
            "description": "Get the full text content of a source in a NotebookLM notebook.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "notebook_id": {"type": "string", "description": "Notebook ID"},
                    "source_id": {"type": "string", "description": "Source ID (from notebooklm_list_sources)"},
                },
                "required": ["notebook_id", "source_id"],
            },
        },
        {
            "name": "notebooklm_list_sources",
            "description": "List all sources in a NotebookLM notebook.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "notebook_id": {"type": "string", "description": "Notebook ID"},
                },
                "required": ["notebook_id"],
            },
        },
        {
            "name": "notebooklm_chat",
            "description": "Ask a question against the sources in a NotebookLM notebook. Returns an answer with source references.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "notebook_id": {"type": "string", "description": "Notebook ID"},
                    "message": {"type": "string", "description": "Question to ask"},
                },
                "required": ["notebook_id", "message"],
            },
        },
        {
            "name": "notebooklm_generate_artifact",
            "description": (
                "Generate an artifact from a NotebookLM notebook. "
                "Types: audio_overview, briefing_doc, study_guide, faq, timeline, mind_map. "
                "Long-running — use 'animaworks-tool submit' for background execution."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "notebook_id": {"type": "string", "description": "Notebook ID"},
                    "artifact_type": {
                        "type": "string",
                        "enum": ["audio_overview", "briefing_doc", "study_guide", "faq", "timeline", "mind_map"],
                        "description": "Type of artifact to generate",
                    },
                    "language": {
                        "type": "string",
                        "description": "Output language (default: en)",
                    },
                    "instructions": {
                        "type": "string",
                        "description": "Custom instructions for generation",
                    },
                },
                "required": ["notebook_id", "artifact_type"],
            },
        },
        {
            "name": "notebooklm_list_artifacts",
            "description": "List artifacts in a NotebookLM notebook.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "notebook_id": {"type": "string", "description": "Notebook ID"},
                    "artifact_type": {
                        "type": "string",
                        "description": "Filter by type (e.g. AUDIO, REPORT, MIND_MAP)",
                    },
                },
                "required": ["notebook_id"],
            },
        },
    ]


# ── Dispatch ──────────────────────────────────────────────


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Dispatch a tool call by schema name."""
    args.pop("anima_dir", None)
    args.pop("_trigger", None)

    try:
        if name == "notebooklm_list_notebooks":
            return _run_async(_list_notebooks())
        if name == "notebooklm_get_notebook":
            return _run_async(_get_notebook(args["notebook_id"]))
        if name == "notebooklm_create_notebook":
            return _run_async(_create_notebook(args["title"]))
        if name == "notebooklm_delete_notebook":
            return _run_async(_delete_notebook(args["notebook_id"]))
        if name == "notebooklm_add_source_url":
            return _run_async(_add_source_url(args["notebook_id"], args["url"]))
        if name == "notebooklm_add_source_text":
            return _run_async(_add_source_text(args["notebook_id"], args["text"], title=args.get("title")))
        if name == "notebooklm_add_source_file":
            return _run_async(_add_source_file(args["notebook_id"], args["file_path"]))
        if name == "notebooklm_get_source_fulltext":
            return _run_async(_get_source_fulltext(args["notebook_id"], args["source_id"]))
        if name == "notebooklm_list_sources":
            return _run_async(_list_sources(args["notebook_id"]))
        if name == "notebooklm_chat":
            return _run_async(_chat(args["notebook_id"], args["message"]))
        if name == "notebooklm_generate_artifact":
            return _run_async(
                _generate_artifact(
                    args["notebook_id"],
                    args["artifact_type"],
                    language=args.get("language", "en"),
                    instructions=args.get("instructions"),
                )
            )
        if name == "notebooklm_list_artifacts":
            return _run_async(_list_artifacts(args["notebook_id"], artifact_type=args.get("artifact_type")))
    except AuthError as exc:
        return {
            "success": False,
            "error": f"Authentication failed: {exc}. Run 'notebooklm login' to re-authenticate.",
        }
    except NotebookLMError as exc:
        return {"success": False, "error": str(exc)}

    raise ValueError(f"Unknown tool: {name}")


# ── CLI ───────────────────────────────────────────────────


def get_cli_guide() -> str:
    """Return CLI usage guide for NotebookLM tools."""
    return """\
### NotebookLM
```bash
animaworks-tool notebooklm list
animaworks-tool notebooklm get <notebook_id>
animaworks-tool notebooklm create "My Notebook"
animaworks-tool notebooklm delete <notebook_id>
animaworks-tool notebooklm add-source-url <notebook_id> <url>
animaworks-tool notebooklm add-source-text <notebook_id> --title "Title" --text "Content"
animaworks-tool notebooklm add-source-file <notebook_id> /path/to/file.pdf
animaworks-tool notebooklm source-text <notebook_id> <source_id>
animaworks-tool notebooklm sources <notebook_id>
animaworks-tool notebooklm chat <notebook_id> "Your question here"
animaworks-tool notebooklm generate <notebook_id> --type audio_overview
animaworks-tool notebooklm artifacts <notebook_id>
```
⚠️ **generate** is long-running. Use `animaworks-tool submit notebooklm generate ...` for background execution."""


def cli_main(argv: list[str] | None = None) -> None:
    """Standalone CLI for NotebookLM operations."""
    parser = argparse.ArgumentParser(
        prog="animaworks-notebooklm",
        description="AnimaWorks NotebookLM tool -- manage notebooks, sources, and artifacts.",
    )
    sub = parser.add_subparsers(dest="command")

    # list notebooks
    sub.add_parser("list", help="List all notebooks")

    # get notebook
    p_get = sub.add_parser("get", help="Get notebook summary and description")
    p_get.add_argument("notebook_id", help="Notebook ID")

    # create
    p_create = sub.add_parser("create", help="Create a new notebook")
    p_create.add_argument("title", help="Notebook title")

    # delete
    p_delete = sub.add_parser("delete", help="Delete a notebook")
    p_delete.add_argument("notebook_id", help="Notebook ID")

    # add-source-url
    p_url = sub.add_parser("add-source-url", help="Add a URL source")
    p_url.add_argument("notebook_id", help="Notebook ID")
    p_url.add_argument("url", help="URL to add")

    # add-source-text
    p_text = sub.add_parser("add-source-text", help="Add a text source")
    p_text.add_argument("notebook_id", help="Notebook ID")
    p_text.add_argument("--title", help="Source title")
    p_text.add_argument("--text", required=True, help="Text content")

    # add-source-file
    p_file = sub.add_parser("add-source-file", help="Add a file source")
    p_file.add_argument("notebook_id", help="Notebook ID")
    p_file.add_argument("file_path", help="Path to the file")

    # source-text
    p_st = sub.add_parser("source-text", help="Get full text of a source")
    p_st.add_argument("notebook_id", help="Notebook ID")
    p_st.add_argument("source_id", help="Source ID")

    # sources
    p_sources = sub.add_parser("sources", help="List sources in a notebook")
    p_sources.add_argument("notebook_id", help="Notebook ID")

    # chat
    p_chat = sub.add_parser("chat", help="Ask a question against notebook sources")
    p_chat.add_argument("notebook_id", help="Notebook ID")
    p_chat.add_argument("message", help="Question to ask")

    # generate
    p_gen = sub.add_parser("generate", help="Generate an artifact")
    p_gen.add_argument("notebook_id", help="Notebook ID")
    p_gen.add_argument(
        "--type",
        dest="artifact_type",
        default="audio_overview",
        choices=["audio_overview", "briefing_doc", "study_guide", "faq", "timeline", "mind_map"],
        help="Artifact type (default: audio_overview)",
    )
    p_gen.add_argument("--language", default="en", help="Output language (default: en)")
    p_gen.add_argument("--instructions", help="Custom instructions")

    # artifacts
    p_arts = sub.add_parser("artifacts", help="List artifacts in a notebook")
    p_arts.add_argument("notebook_id", help="Notebook ID")
    p_arts.add_argument("--type", dest="artifact_type", help="Filter by artifact type")

    ns = parser.parse_args(argv)

    if not ns.command:
        parser.print_help()
        sys.exit(1)

    try:
        if ns.command == "list":
            result = _run_async(_list_notebooks())
        elif ns.command == "get":
            result = _run_async(_get_notebook(ns.notebook_id))
        elif ns.command == "create":
            result = _run_async(_create_notebook(ns.title))
        elif ns.command == "delete":
            result = _run_async(_delete_notebook(ns.notebook_id))
        elif ns.command == "add-source-url":
            result = _run_async(_add_source_url(ns.notebook_id, ns.url))
        elif ns.command == "add-source-text":
            result = _run_async(_add_source_text(ns.notebook_id, ns.text, title=ns.title))
        elif ns.command == "add-source-file":
            result = _run_async(_add_source_file(ns.notebook_id, ns.file_path))
        elif ns.command == "source-text":
            result = _run_async(_get_source_fulltext(ns.notebook_id, ns.source_id))
        elif ns.command == "sources":
            result = _run_async(_list_sources(ns.notebook_id))
        elif ns.command == "chat":
            result = _run_async(_chat(ns.notebook_id, ns.message))
        elif ns.command == "generate":
            result = _run_async(
                _generate_artifact(
                    ns.notebook_id,
                    ns.artifact_type,
                    language=ns.language,
                    instructions=ns.instructions,
                )
            )
        elif ns.command == "artifacts":
            result = _run_async(_list_artifacts(ns.notebook_id, artifact_type=ns.artifact_type))
        else:
            parser.print_help()
            sys.exit(1)

        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except AuthError as exc:
        print(f"Auth error: {exc}. Run 'notebooklm login' to re-authenticate.", file=sys.stderr)
        sys.exit(1)
    except NotebookLMError as exc:
        print(f"NotebookLM error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    cli_main()
