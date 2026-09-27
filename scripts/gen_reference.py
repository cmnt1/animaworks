#!/usr/bin/env python3
"""Generate deterministic Japanese reference documentation from source code."""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import importlib
import inspect
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import tokenize
import types
from collections import defaultdict
from pathlib import Path
from typing import Any, get_args, get_origin

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
if not os.environ.get("ANIMAWORKS_DATA_DIR"):
    os.environ["ANIMAWORKS_DATA_DIR"] = tempfile.mkdtemp(prefix="animaworks-reference-")

import yaml

logger = logging.getLogger(__name__)

GENERATOR_VERSION = "gen_reference/1"
OUTPUT_DIR = PROJECT_DIR / "docs" / "ja" / "reference"
DICTIONARY_DIR = PROJECT_DIR / "scripts" / "reference_ja"
KINDS = ("cli", "tool-cli", "api", "config", "modules")
REGEN_COMMANDS = {
    "cli": "uv run python scripts/gen_reference.py cli",
    "tool-cli": "uv run python scripts/gen_reference.py tool-cli",
    "api": "uv run python scripts/gen_reference.py api",
    "config": "uv run python scripts/gen_reference.py config",
    "modules": "uv run python scripts/gen_reference.py modules",
    "all": "uv run python scripts/gen_reference.py all",
    "templates": "uv run python scripts/gen_reference.py templates",
}


class ReferenceGenerationError(Exception):
    """Raised when source metadata or an explanation dictionary is invalid."""


def ensure_isolated_data_dir() -> Path:
    """Set a private runtime directory before importing application modules."""
    current = os.environ.get("ANIMAWORKS_DATA_DIR")
    if current:
        return Path(current)
    data_dir = Path(tempfile.mkdtemp(prefix="animaworks-reference-"))
    os.environ["ANIMAWORKS_DATA_DIR"] = str(data_dir)
    return data_dir


def _load_dictionary(kind: str) -> tuple[dict[str, Any], bytes]:
    path = DICTIONARY_DIR / f"{kind}.yaml"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ReferenceGenerationError(f"Missing explanation dictionary: {path}") from exc
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ReferenceGenerationError(f"Expected a YAML mapping in {path}")
    return data, raw


def _markdown_cell(value: Any) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    return text.replace("|", "\\|")


def _normalise(value: Any) -> Any:
    """Return JSON-compatible deterministic data and redact machine home paths."""
    from pydantic import BaseModel

    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str):
            home = str(Path.home())
            return value.replace(home, "~") if home and home != "/" else value
        return value
    if isinstance(value, Path):
        return _normalise(str(value))
    if isinstance(value, BaseModel):
        return {"model": type(value).__name__}
    if isinstance(value, dict):
        return {str(key): _normalise(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (set, frozenset)):
        return sorted((_normalise(item) for item in value), key=str)
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    if hasattr(value, "value"):
        return _normalise(value.value)
    return str(value)


def _json(value: Any) -> str:
    return json.dumps(_normalise(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _source_hash(payload: Any, dictionary_raw: bytes) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256()
    digest.update(GENERATOR_VERSION.encode())
    digest.update(b"\0")
    digest.update(canonical)
    digest.update(b"\0")
    digest.update(dictionary_raw)
    return digest.hexdigest()


def _with_header(kind: str, body: str, payload: Any, dictionary_raw: bytes) -> str:
    digest = _source_hash(payload, dictionary_raw)
    header = (
        f"<!-- 自動生成ファイル・編集禁止。再生成: {REGEN_COMMANDS[kind]} -->\n"
        f"<!-- generator: {GENERATOR_VERSION}  kind: {kind}  source-sha256: {digest} -->\n\n"
    )
    return header + body.rstrip() + "\n"


def _description(mapping: dict[str, Any], key: str, fallback: Any = None) -> str:
    value = mapping.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return "—"


def _validate_dictionary_keys(kind: str, dictionary: dict[str, Any], valid_keys: set[str]) -> None:
    special = {"status_json_extra"} if kind == "config" else set()
    stale = sorted(set(dictionary) - valid_keys - special)
    if stale:
        raise ReferenceGenerationError(f"Stale {kind} explanation key(s): {', '.join(stale)}")


def _argparse_default(value: Any) -> str:
    import argparse

    if value is argparse.SUPPRESS:
        return ""
    if value is None:
        return "—"
    return _markdown_cell(_json(value))


def extract_cli() -> tuple[str, Any, list[str]]:
    """Extract the argparse command tree without running cli_main side effects."""
    from cli.parser import build_parser

    dictionary, dictionary_raw = _load_dictionary("cli")
    parser = build_parser()
    import argparse

    commands: list[dict[str, Any]] = []
    missing: list[str] = []

    def parser_arguments(command_parser: argparse.ArgumentParser, path: str) -> list[dict[str, str]]:
        rows = []
        for action in command_parser._actions:
            if isinstance(action, argparse._SubParsersAction) or action.dest == "help":
                continue
            if action.default is argparse.SUPPRESS:
                continue
            name = ", ".join(action.option_strings) if action.option_strings else action.dest
            if action.nargs == 0:
                arg_type = "flag"
            elif action.option_strings:
                arg_type = "option"
            else:
                arg_type = "positional"
            choices = ", ".join(str(choice) for choice in action.choices) if action.choices is not None else "—"
            help_text = action.help if isinstance(action.help, str) else "—"
            rows.append(
                {
                    "name": name,
                    "type": arg_type,
                    "default": _argparse_default(action.default) or "—",
                    "choices": _markdown_cell(choices),
                    "description": _description(dictionary, f"{path} {name}", help_text),
                }
            )
        return rows

    def visit(command_parser: argparse.ArgumentParser, path: str, help_text: str = "") -> None:
        if path:
            fallback = command_parser.description or help_text
            desc = _description(dictionary, path, fallback)
            if desc == "—":
                missing.append(path)
            commands.append(
                {
                    "path": path,
                    "description": desc,
                    "usage": command_parser.format_usage().strip(),
                    "arguments": parser_arguments(command_parser, path),
                }
            )
        for action in command_parser._actions:
            if not isinstance(action, argparse._SubParsersAction):
                continue
            for name, child in action.choices.items():
                child_path = f"{path} {name}".strip()
                visit(child, child_path, _subparser_help(action, name))

    visit(parser, "")
    commands.sort(key=lambda item: item["path"])
    valid_keys = {item["path"] for item in commands}
    _validate_dictionary_keys("cli", dictionary, valid_keys)
    root_args = parser_arguments(parser, "animaworks")
    for command in commands:
        for argument in command["arguments"]:
            if argument["description"] == "—":
                missing.append(f"{command['path']} {argument['name']}")

    lines = [
        "# CLI リファレンス: `animaworks`",
        "",
        "`animaworks` コマンドの argparse 定義から生成しています。",
        "",
        "## グローバルオプション",
        "",
        "| 名前 | 種別 | 既定値 | 選択肢 | 説明 |",
        "|---|---|---|---|---|",
    ]
    lines.extend(_argument_row(row) for row in root_args)
    for command in commands:
        lines.extend(
            [
                "",
                f"## `{command['path']}`",
                "",
                f"{command['description']}",
                "",
                f"`{command['usage']}`",
                "",
                "| 名前 | 種別 | 既定値 | 選択肢 | 説明 |",
                "|---|---|---|---|---|",
            ]
        )
        if command["arguments"]:
            lines.extend(_argument_row(row) for row in command["arguments"])
        else:
            lines.append("| — | — | — | — | — |")
    payload = {"root_arguments": root_args, "commands": commands}
    return "\n".join(lines), payload, sorted(set(missing))


def _subparser_help(action: Any, name: str) -> str:
    for choice_action in getattr(action, "_choices_actions", []):
        if choice_action.dest == name:
            return choice_action.help or ""
    return ""


def _argument_row(row: dict[str, str]) -> str:
    return (
        "| "
        + " | ".join(_markdown_cell(row[key]) for key in ("name", "type", "default", "choices", "description"))
        + " |"
    )


def extract_tool_cli() -> tuple[str, Any, bytes]:
    from core.integrations import TOOL_MODULES

    tools: list[dict[str, Any]] = []
    for tool_name, module_name in sorted(TOOL_MODULES.items()):
        module = importlib.import_module(module_name)
        getter = getattr(module, "get_tool_schemas", None)
        if not callable(getter):
            continue
        try:
            schemas = getter()
        except Exception as exc:
            logger.warning("Could not read tool schemas from %s: %s", module_name, exc)
            continue
        for schema in schemas or []:
            input_schema = schema.get("input_schema", schema.get("parameters", {}))
            properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
            required = set(input_schema.get("required", [])) if isinstance(input_schema, dict) else set()
            tools.append(
                {
                    "module": tool_name,
                    "name": schema.get("name", tool_name),
                    "description": schema.get("description", "—"),
                    "arguments": [
                        {
                            "name": arg_name,
                            "type": arg_schema.get("type", "—"),
                            "required": arg_name in required,
                            "description": arg_schema.get("description", "—"),
                        }
                        for arg_name, arg_schema in sorted(properties.items())
                    ],
                }
            )
    tools.sort(key=lambda item: (item["module"], item["name"]))
    lines = [
        "# ツール CLI リファレンス: `animaworks-tool`",
        "",
        "`animaworks-tool` は core の外部ツールスキーマから生成しています。common / personal tool は runtime 依存のため対象外です。",
        "",
        "## `submit` によるバックグラウンド実行",
        "",
        "`animaworks-tool submit <tool_name> [args...]` は長時間実行するツールを pending task として登録し、完了結果を inbox に届けます。実行には `ANIMAWORKS_ANIMA_DIR` が必要です。",
    ]
    for tool in tools:
        lines.extend(
            [
                "",
                f"## `{tool['name']}`",
                "",
                f"{tool['description']}",
                "",
                "| 引数 | 型 | 必須 | 説明 |",
                "|---|---|---|---|",
            ]
        )
        if tool["arguments"]:
            for argument in tool["arguments"]:
                required_text = "はい" if argument["required"] else "いいえ"
                lines.append(
                    f"| `{argument['name']}` | {_markdown_cell(argument['type'])} | {required_text} | {_markdown_cell(argument['description'])} |"
                )
        else:
            lines.append("| — | — | — | — |")
    payload = {"tools": tools, "submit": "animaworks-tool submit <tool_name> [args...]"}
    return "\n".join(lines), payload, b""


def _iter_router_routes(router: Any, prefix: str = "", include_in_schema: bool = True):
    """Recursively walk FastAPI's lazy ``_IncludedRouter`` graph."""
    for route in router.routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            context = route.include_context
            yield from _iter_router_routes(
                original_router,
                prefix + context.prefix,
                include_in_schema and context.include_in_schema,
            )
            continue
        path = prefix + getattr(route, "path", "")
        yield route, path, include_in_schema


def _route_source(endpoint: Any) -> str:
    module = getattr(endpoint, "__module__", "")
    function = getattr(endpoint, "__name__", getattr(endpoint, "__qualname__", "unknown"))
    if module.startswith("server."):
        source_path = module.replace(".", "/") + ".py"
    else:
        source_path = module
    return f"{source_path}:{function}"


def _first_doc_line(endpoint: Any) -> str:
    doc = inspect.getdoc(endpoint) or ""
    return next((line.strip() for line in doc.splitlines() if line.strip()), "")


def _direct_app_routes() -> list[dict[str, Any]]:
    app_path = PROJECT_DIR / "server" / "app.py"
    tree = ast.parse(app_path.read_text(encoding="utf-8"))
    records = []
    known_methods = {
        "get": "GET",
        "post": "POST",
        "put": "PUT",
        "patch": "PATCH",
        "delete": "DELETE",
        "head": "HEAD",
        "options": "OPTIONS",
        "websocket": "WS",
    }
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node) or ""
        description = next((line.strip() for line in doc.splitlines() if line.strip()), "")
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "app":
                continue
            route_method = decorator.func.attr.lower()
            if route_method not in known_methods and route_method != "api_route":
                continue
            path = decorator.args[0].value if decorator.args and isinstance(decorator.args[0], ast.Constant) else None
            if not isinstance(path, str):
                continue
            methods = [known_methods[route_method]] if route_method in known_methods else []
            include_in_schema = True
            for keyword in decorator.keywords:
                if keyword.arg == "include_in_schema" and isinstance(keyword.value, ast.Constant):
                    include_in_schema = bool(keyword.value.value)
                if keyword.arg == "methods" and isinstance(keyword.value, (ast.List, ast.Tuple)):
                    methods = [
                        known_methods.get(item.value.lower(), item.value.upper())
                        for item in keyword.value.elts
                        if isinstance(item, ast.Constant) and isinstance(item.value, str)
                    ]
            for method in methods:
                records.append(
                    {
                        "method": method,
                        "path": path,
                        "source": f"server/app.py:{node.name}",
                        "description": description,
                        "include_in_schema": include_in_schema,
                    }
                )
    return records


def _auth_classification(method: str, path: str) -> str:
    from server.app import _AUTH_WHITELIST_PREFIXES, _PUBLIC_ICON_ASSET_PATH

    if any(path.startswith(prefix) for prefix in _AUTH_WHITELIST_PREFIXES):
        return "不要（除外一覧）"
    if method in {"GET", "HEAD"} and _PUBLIC_ICON_ASSET_PATH.match(path):
        return "不要（公開アイコン、GET/HEAD）"
    if path.startswith("/api/internal/"):
        return "内部"
    if path.startswith("/api/") or path == "/ws" or path.startswith("/ws/"):
        return "セッション必須（local_trust モード、または localhost 信頼が有効なら省略可）"
    return "不要"


def extract_api() -> tuple[str, Any, list[str]]:
    from fastapi import FastAPI
    from fastapi.routing import APIRoute
    from starlette.routing import WebSocketRoute

    from server.routes import create_router
    from server.routes.setup import create_setup_router

    dictionary, dictionary_raw = _load_dictionary("api")
    app = FastAPI()
    app.include_router(create_router())
    app.include_router(create_setup_router())
    openapi = app.openapi()

    routes_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    websocket_records: list[dict[str, Any]] = []
    for route, full_path, include_in_schema in _iter_router_routes(app.router):
        if isinstance(route, APIRoute):
            for method in sorted(route.methods or []):
                routes_by_key[(method, full_path)] = {
                    "source": _route_source(route.endpoint),
                    "description": _first_doc_line(route.endpoint),
                    "include_in_schema": include_in_schema and route.include_in_schema,
                }
        elif isinstance(route, WebSocketRoute):
            websocket_records.append(
                {
                    "method": "WS",
                    "path": full_path,
                    "source": _route_source(route.endpoint),
                    "description": _first_doc_line(route.endpoint),
                    "include_in_schema": False,
                }
            )

    records: dict[tuple[str, str], dict[str, Any]] = {}
    operation_ids: dict[str, list[str]] = defaultdict(list)
    for path, path_item in openapi.get("paths", {}).items():
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options", "trace"}:
                continue
            upper_method = method.upper()
            route_info = routes_by_key.get((upper_method, path), {})
            operation_id = operation.get("operationId")
            if operation_id:
                operation_ids[operation_id].append(f"{upper_method} {path}")
            records[(upper_method, path)] = {
                "method": upper_method,
                "path": path,
                "source": route_info.get("source", "server/routes (OpenAPI)"),
                "description": route_info.get("description") or operation.get("description", "").split("\n", 1)[0],
            }

    for (method, path), route_info in routes_by_key.items():
        if route_info["include_in_schema"] and (method, path) in records:
            continue
        records.setdefault(
            (method, path),
            {"method": method, "path": path, "source": route_info["source"], "description": route_info["description"]},
        )
    for record in _direct_app_routes():
        records.setdefault((record["method"], record["path"]), record)
    for record in websocket_records:
        records.setdefault((record["method"], record["path"]), record)

    for operation_id, locations in sorted(operation_ids.items()):
        if len(locations) > 1:
            print(f"WARNING: duplicate OpenAPI operationId {operation_id}: {', '.join(locations)}", file=sys.stderr)

    entries = sorted(records.values(), key=lambda item: (item["source"].split(":", 1)[0], item["path"], item["method"]))
    valid_keys = {f"{entry['method']} {entry['path']}" for entry in entries}
    _validate_dictionary_keys("api", dictionary, valid_keys)
    missing = []
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for entry in entries:
        key = f"{entry['method']} {entry['path']}"
        fallback = entry.get("description")
        description = _description(dictionary, key, fallback)
        if description == "—":
            missing.append(key)
        groups[entry["source"].split(":", 1)[0]].append(
            {
                "method": entry["method"],
                "path": entry["path"],
                "auth": _auth_classification(entry["method"], entry["path"]),
                "description": description,
                "source": entry["source"],
            }
        )

    lines = [
        "# API リファレンス",
        "",
        "FastAPI の OpenAPI 定義、WebSocket、`server/app.py` の直書きルートから生成しています。",
        "",
        "| メソッド | パス | 認証区分 | 概要 | 定義位置 |",
        "|---|---|---|---|---|",
    ]
    for source_file in sorted(groups):
        lines.extend(["", f"## `{source_file}`", ""])
        for item in groups[source_file]:
            lines.append(
                f"| {item['method']} | `{item['path']}` | {item['auth']} | {_markdown_cell(item['description'])} | `{item['source']}` |"
            )
    payload = {
        "operations": entries,
        "auth_whitelist": sorted(
            __import__("server.app", fromlist=["_AUTH_WHITELIST_PREFIXES"])._AUTH_WHITELIST_PREFIXES
        ),
    }
    return "\n".join(lines), payload, sorted(set(missing))


def _annotation_text(annotation: Any) -> str:
    origin = get_origin(annotation)
    if origin is None:
        if annotation is type(None):
            return "None"
        if isinstance(annotation, type):
            return annotation.__name__
        return str(annotation).replace("typing.", "")
    args = get_args(annotation)
    if origin is list:
        return f"list[{_annotation_text(args[0])}]" if args else "list"
    if origin is dict:
        return f"dict[{', '.join(_annotation_text(arg) for arg in args)}]"
    if origin is tuple:
        return f"tuple[{', '.join(_annotation_text(arg) for arg in args)}]"
    if getattr(origin, "__name__", "") == "Literal":
        return "Literal[" + ", ".join(repr(arg) for arg in args) + "]"
    if str(origin).endswith("Union") or origin is types.UnionType:
        return " | ".join(_annotation_text(arg) for arg in args)
    return f"{getattr(origin, '__name__', str(origin))}[{', '.join(_annotation_text(arg) for arg in args)}]"


def _line_comments(source_paths: list[Path]) -> dict[tuple[str, int], str]:
    comments: dict[tuple[str, int], str] = {}
    for path in source_paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        class_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        token_comments = {
            token.start[0]: token.string[1:].strip()
            for token in tokenize.generate_tokens(io.StringIO(source).readline)
            if token.type == tokenize.COMMENT
        }
        for class_node in class_nodes:
            for node in class_node.body:
                if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    text = token_comments.get(node.lineno)
                    if text:
                        comments[(class_node.name, node.lineno)] = text
    return comments


def _field_default(field: Any) -> Any:
    from pydantic_core import PydanticUndefined

    if field.default_factory is not None:
        try:
            return field.default_factory()
        except Exception:
            return "<factory>"
    if field.default is PydanticUndefined:
        return "—"
    return field.default


def _display_default(value: Any) -> str:
    from pydantic import BaseModel

    if isinstance(value, BaseModel):
        return "{" + type(value).__name__ + "}"
    normalised = _normalise(value)
    if isinstance(normalised, (dict, list)) and len(_json(normalised)) > 120:
        return "…"
    return _markdown_cell(_json(normalised))


def _nested_model(annotation: Any):
    from pydantic import BaseModel

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in get_args(annotation):
        if isinstance(arg, type) and issubclass(arg, BaseModel):
            return arg
    return None


def extract_config() -> tuple[str, Any, list[str]]:
    from pydantic import BaseModel

    from core.config.resolver import STATUS_JSON_FIELD_MAP
    from core.config.schemas import AnimaWorksConfig
    from core.schemas import ModelConfig

    dictionary, dictionary_raw = _load_dictionary("config")
    required_sections = set(AnimaWorksConfig.model_fields)
    missing_sections = sorted(required_sections - set(dictionary))
    if missing_sections:
        raise ReferenceGenerationError(f"Missing required AnimaWorksConfig descriptions: {', '.join(missing_sections)}")
    source_paths = [PROJECT_DIR / "core" / "config" / "schemas.py", PROJECT_DIR / "core" / "schemas.py"]
    comments = _line_comments(source_paths)
    rows: list[dict[str, Any]] = []

    def walk_model(model: type[BaseModel], prefix: str = "") -> None:
        source_file = source_paths[1] if model.__module__ == "core.schemas" else source_paths[0]
        model_source = source_file.read_text(encoding="utf-8")
        class_line = next(
            (
                node.lineno
                for node in ast.parse(model_source).body
                if isinstance(node, ast.ClassDef) and node.name == model.__name__
            ),
            0,
        )
        for field_name, field in model.model_fields.items():
            key = f"{prefix}.{field_name}" if prefix else field_name
            field_line = _field_declaration_line(model_source, model.__name__, field_name, class_line)
            comment = comments.get((model.__name__, field_line), "")
            fallback = field.description or comment
            rows.append(
                {
                    "key": key,
                    "type": _annotation_text(field.annotation),
                    "default": _display_default(_field_default(field)),
                    "description": _description(dictionary, key, fallback),
                    "model": model.__name__,
                }
            )
            nested = _nested_model(field.annotation)
            if nested is not None and nested is not model:
                walk_model(nested, key)

    walk_model(AnimaWorksConfig)
    config_keys = {row["key"] for row in rows}
    status_extra = dictionary.get("status_json_extra", {})
    if not isinstance(status_extra, dict):
        raise ReferenceGenerationError("config.yaml status_json_extra must be a mapping")

    model_fields = ModelConfig.model_fields
    status_rows: list[dict[str, Any]] = []
    for status_key, config_key in sorted(STATUS_JSON_FIELD_MAP.items()):
        field = model_fields.get(config_key)
        status_rows.append(
            {
                "key": status_key,
                "type": _annotation_text(field.annotation) if field else "—",
                "default": _display_default(_field_default(field)) if field else "—",
                "description": _description(
                    dictionary, f"status_json.{status_key}", (field.description if field else "")
                ),
            }
        )
    for status_key, description in sorted(status_extra.items()):
        if not isinstance(status_key, str) or not isinstance(description, str):
            raise ReferenceGenerationError("status_json_extra entries must be string keys and descriptions")
        status_rows.append({"key": status_key, "type": "—", "default": "—", "description": description.strip() or "—"})

    valid_keys = config_keys | {f"status_json.{key}" for key in STATUS_JSON_FIELD_MAP} | set(status_extra)
    _validate_dictionary_keys("config", dictionary, valid_keys)
    source_files = _tracked_python_files(["core", "cli", "server"])
    source_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in source_files)
    for extra_key in status_extra:
        if f'"{extra_key}"' not in source_text and f"'{extra_key}'" not in source_text:
            raise ReferenceGenerationError(
                f"status_json_extra key {extra_key!r} is not referenced in core/, cli/, or server/"
            )

    models_path = PROJECT_DIR / "templates" / "_shared" / "config_defaults" / "models.json"
    models_data = json.loads(models_path.read_text(encoding="utf-8"))
    missing = [row["key"] for row in rows if row["description"] == "—"]
    missing.extend(f"status_json.{row['key']}" for row in status_rows if row["description"] == "—")
    lines = [
        "# 設定リファレンス",
        "",
        "`AnimaWorksConfig`、per-anima `ModelConfig`、`models.json` の定義から生成しています。",
        "",
        "## `config.json`",
        "",
        "| キー | 型 | 既定値 | 説明 |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['key']}` | `{_markdown_cell(row['type'])}` | `{_markdown_cell(row['default'])}` | {_markdown_cell(row['description'])} |"
        )
    lines.extend(
        [
            "",
            "## anima ごとの `status.json`",
            "",
            "| キー | ModelConfig 型 | 既定値 | 説明 |",
            "|---|---|---|---|",
        ]
    )
    for row in status_rows:
        lines.append(
            f"| `{row['key']}` | `{_markdown_cell(row['type'])}` | `{_markdown_cell(row['default'])}` | {_markdown_cell(row['description'])} |"
        )
    lines.extend(
        [
            "",
            "## `models.json`",
            "",
            "モデル名パターンごとの実行モードとコンテキストウィンドウです。",
            "",
            "| モデル名パターン | モード | コンテキストウィンドウ |",
            "|---|---|---:|",
        ]
    )
    for pattern, config in sorted(models_data.items()):
        lines.append(
            f"| `{_markdown_cell(pattern)}` | `{_markdown_cell(config.get('mode', '—'))}` | {_markdown_cell(config.get('context_window', '—'))} |"
        )
    payload = {"config": rows, "status_json": status_rows, "models_json": models_data}
    return "\n".join(lines), payload, sorted(missing)


def _field_declaration_line(source: str, class_name: str, field_name: str, class_line: int) -> int:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if (
                    isinstance(child, ast.AnnAssign)
                    and isinstance(child.target, ast.Name)
                    and child.target.id == field_name
                ):
                    return child.lineno
    return class_line


def _tracked_python_files(roots: list[str]) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", *roots],
            cwd=PROJECT_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
        files = [PROJECT_DIR / name for name in result.stdout.splitlines() if name.endswith(".py")]
        if files:
            return files
    except (OSError, subprocess.CalledProcessError):
        pass
    candidates = [
        path for root in roots for path in (PROJECT_DIR / root).rglob("*.py") if "__pycache__" not in path.parts
    ]
    package_dirs = {path.parent for path in candidates if path.name == "__init__.py"}
    return sorted(path for path in candidates if path.name == "__init__.py" or path.parent in package_dirs)


def extract_modules() -> tuple[str, Any, list[str]]:
    dictionary, dictionary_raw = _load_dictionary("modules")
    files = _tracked_python_files(["core", "cli", "server"])
    package_files: dict[str, list[dict[str, Any]]] = defaultdict(list)
    core_packages: set[str] = set()
    for path in files:
        relative = path.relative_to(PROJECT_DIR).as_posix()
        if not relative.endswith(".py"):
            continue
        parts = relative[:-3].split("/")
        if parts[-1] == "__init__":
            module_parts = parts[:-1]
        else:
            module_parts = parts
        if not module_parts:
            continue
        if parts[-1] == "__init__":
            package = ".".join(module_parts)
        elif len(module_parts) > 2:
            package = ".".join(module_parts[:2])
        else:
            package = module_parts[0]
        if relative.startswith("core/") and len(parts) > 2 and parts[1] != "__init__":
            if (PROJECT_DIR / "core" / parts[1] / "__init__.py").exists():
                core_packages.add(f"core.{parts[1]}")
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source)
            doc = ast.get_docstring(tree) or ""
        except SyntaxError:
            doc = ""
        first_line = next((line.strip() for line in doc.splitlines() if line.strip()), "—")
        module_name = ".".join(module_parts)
        private = any(part.startswith("_") and part != "__init__" for part in parts)
        if private:
            module_name += "（非公開）"
        package_files[package].append(
            {
                "module": module_name,
                "lines": len(source.splitlines()),
                "description": first_line,
                "private": private,
            }
        )
    _validate_dictionary_keys("modules", dictionary, core_packages)
    absent = sorted(core_packages - set(dictionary))
    if absent:
        raise ReferenceGenerationError(f"Missing required core package descriptions: {', '.join(absent)}")

    missing: list[str] = []
    lines = [
        "# モジュール一覧",
        "",
        "`git ls-files core cli server` で追跡対象の Python ファイルを列挙しています。非公開モジュールには印を付けています。",
    ]
    for package in sorted(package_files):
        package_description = _description(dictionary, package)
        if package.startswith("core.") and package_description == "—":
            missing.append(package)
        lines.extend(
            [
                "",
                f"## `{package}`",
                "",
                package_description,
                "",
                "| モジュール | 行数 | docstring 1行目 |",
                "|---|---:|---|",
            ]
        )
        for item in sorted(package_files[package], key=lambda item: item["module"]):
            lines.append(f"| `{item['module']}` | {item['lines']} | {_markdown_cell(item['description'])} |")
            if item["description"] == "—":
                missing.append(item["module"])
    payload = {
        "packages": {
            key: sorted(value, key=lambda item: item["module"]) for key, value in sorted(package_files.items())
        }
    }
    return "\n".join(lines), payload, sorted(set(missing))


def _make_reference(kind: str) -> tuple[str, list[str]]:
    if kind == "cli":
        body, payload, missing = extract_cli()
        dictionary, raw = _load_dictionary("cli")
    elif kind == "tool-cli":
        body, payload, raw = extract_tool_cli()
        missing = []
    elif kind == "api":
        body, payload, missing = extract_api()
        dictionary, raw = _load_dictionary("api")
    elif kind == "config":
        body, payload, missing = extract_config()
        dictionary, raw = _load_dictionary("config")
    elif kind == "modules":
        body, payload, missing = extract_modules()
        dictionary, raw = _load_dictionary("modules")
    else:
        raise ReferenceGenerationError(f"Unknown reference kind: {kind}")
    if kind == "tool-cli":
        return _with_header(kind, body, payload, raw), missing
    return _with_header(kind, body, payload, raw), missing


def _render_index(references: dict[str, str]) -> str:
    lines = ["# リファレンス", "", "コードから自動生成された日本語の参照資料です。", "", "| 資料 | 内容 |", "|---|---|"]
    labels = {
        "cli": ("CLI", "`animaworks` のコマンドと引数"),
        "tool-cli": ("ツール CLI", "`animaworks-tool` と外部ツールの引数"),
        "api": ("API", "HTTP / WebSocket API と認証区分"),
        "config": ("設定", "config.json、status.json、models.json"),
        "modules": ("モジュール", "core / cli / server の Python モジュール構成"),
    }
    for kind in KINDS:
        label, description = labels[kind]
        lines.append(f"| [{label}]({kind}.md) | {description} |")
    return "\n".join(lines)


def _check_or_write(path: Path, expected: str, check: bool, command: str) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if current == expected:
        return True
    if check:
        print(f"Generated reference is stale: {path.relative_to(PROJECT_DIR)}", file=sys.stderr)
        diff = list(
            difflib.unified_diff(
                current.splitlines(),
                expected.splitlines(),
                fromfile=str(path),
                tofile="generated",
                lineterm="",
            )
        )
        for line in diff[:40]:
            print(line, file=sys.stderr)
        print(f"Regenerate with: {command}", file=sys.stderr)
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(expected, encoding="utf-8")
    logger.info("Wrote %s", path.relative_to(PROJECT_DIR))
    return True


def _templates(check: bool) -> bool:
    from scripts.generate_reference import process_directory

    templates_dir = PROJECT_DIR / "templates" / "ja"
    modified = process_directory(templates_dir, dry_run=check)
    if check and modified:
        print(
            "Template reference sections are stale. Regenerate with: uv run python scripts/gen_reference.py templates",
            file=sys.stderr,
        )
        return False
    return True


def _report_missing(kind: str) -> int:
    if kind == "all":
        requested = ["cli", "api", "config", "modules"]
    elif kind in {"cli", "api", "config", "modules"}:
        requested = [kind]
    else:
        requested = []
    missing_by_kind: dict[str, list[str]] = {}
    payloads: dict[str, Any] = {}
    extractors = {
        "cli": extract_cli,
        "api": extract_api,
        "config": extract_config,
        "modules": extract_modules,
    }
    for item in requested:
        _, payload, missing = extractors[item]()
        missing_by_kind[item] = missing
        payloads[item] = payload
    for item, missing in missing_by_kind.items():
        if item == "config":
            direct_missing = [
                row["key"]
                for row in payloads[item]["config"]
                if row["model"] == "AnimaWorksConfig" and row["description"] == "—"
            ]
            print(f"AnimaWorksConfig direct sections: {len(direct_missing)} missing")
        elif item == "modules":
            dictionary, _ = _load_dictionary("modules")
            direct_packages = [
                key for key in payloads[item]["packages"] if key.startswith("core.") and key.count(".") == 1
            ]
            required_missing = sorted(set(direct_packages) - set(dictionary))
            print(f"core/ direct package descriptions: {len(required_missing)} missing")
        print(f"{item}: {len(missing)} missing description(s)")
        for key in missing:
            print(f"  {key}")
    return 0


def run(kind: str, *, check: bool = False, report_missing: bool = False) -> int:
    ensure_isolated_data_dir()
    if report_missing:
        return _report_missing(kind)
    requested = list(KINDS) if kind == "all" else [kind]
    success = True
    rendered: dict[str, str] = {}
    for item in requested:
        if item == "templates":
            success = _templates(check) and success
            continue
        content, _ = _make_reference(item)
        rendered[item] = content
        success = _check_or_write(OUTPUT_DIR / f"{item}.md", content, check, REGEN_COMMANDS[item]) and success
    if kind == "all":
        index_body = _render_index(rendered)
        index_payload = {
            name: hashlib.sha256(content.encode()).hexdigest() for name, content in sorted(rendered.items())
        }
        index = _with_header("all", index_body, index_payload, b"")
        success = _check_or_write(OUTPUT_DIR / "README.md", index, check, REGEN_COMMANDS["all"]) and success
        success = _templates(check) and success
    return 0 if success else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic Japanese reference documentation.")
    parser.add_argument("kind", choices=(*KINDS, "templates", "all"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Write generated files (the default).")
    mode.add_argument("--check", action="store_true", help="Check that committed generated files are fresh.")
    parser.add_argument("--report-missing", action="store_true", help="List items whose resolved description is —.")
    args = parser.parse_args()
    try:
        status = run(args.kind, check=args.check, report_missing=args.report_missing)
    except ReferenceGenerationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    raise SystemExit(status)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
