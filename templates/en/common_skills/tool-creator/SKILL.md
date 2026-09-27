---
name: tool-creator
description: >-
  A meta-skill for creating Python external tool modules for AnimaWorks.core/toolsHandles integration, get_credential, and permissions.
  Use when: Use when: adding a new module to core/tools, implementing a Web API wrapper, or developing custom tools called from animaworks-tool.
---
Understood. I’m ready to translate the Japanese content into natural English while preserving all Markdown structure, headings, tables, links, identifiers, sentinels (including ⟦§number⟧ markers), and YAML frontmatter keys. I’ll keep the prefix “Use when:” unchanged and translate only exposed values. Please provide the content to translate.# tool-creator## 概要

AnimaWorksのツールは3種類に分かれる:

| 種類 | 配置先 | 発見方法 |
|------|--------|----------|
| **コアツール** | `core/integrations/*.py`（`_` 接頭辞のファイルは除外） | `discover_core_tools()` → `TOOL_MODULES`（パッケージ import） |
| **共有ツール** | `{data_dir}/common_tools/*.py` | `discover_common_tools()` |
| **個人ツール** | `{anima_dir}/tools/*.py` | `discover_personal_tools()` |

`{data_dir}` は通常 `~/.animaworks/`。

- **ディスパッチ**: `ExternalToolDispatcher` は `_DISPATCH_TABLE` を廃止し、各モジュールの `dispatch(name, args)`（またはスキーマ名と同名の関数）に統一している（`core/tooling/dispatch.py`）。
- **マージ**: `AgentCore` 起動時の `_discover_personal_tools()` と `refresh_tools` はいずれも **共通→個人** の順でマージし、**個人が同名を上書き** する（`{**common, **personal}`）。マージ結果は `ExternalToolDispatcher` の `_personal_tools` に保持される（名前は historical だが **共通ツールも含む**）。
- **コアとの衝突**: コア `TOOL_MODULES` と同名のファイルは、共通・個人の発見時に **スキップ** される（警告ログのみ）。
- **ツールファイルの書き込み**: `write_memory_file` で `tools/*.py` に書くときは `permissions`（**`permissions.json` 優先**）の **tool_creation.personal** を満たす必要がある（`core/tooling/handler_memory.py`）。

## Execution Path (How it is called from the LLM)

| Mode | Typical Route |
|--------|-----------|
| **A (LiteLLM, etc.)** | Integration tool **`use_tool(tool_name, action, args)`** → module's `dispatch` (`core/tooling/handler.py`). For details, see **`read_memory_file`** for reading each tool's skills (`core/tooling/schemas/skill.py`'s `USE_TOOL`). |
| **S (Agent SDK)** | Via Claude Code's built-in **Bash** for `animaworks-tool <ツール> …`, or via MCP (only a curated subset is available on MCP; see "Adding core tools to the repository" below). |
| **Anthropic fallback, etc.** | `build_tool_list` may have a configuration for `include_use_tool=False` → externally, it relies on **Bash + animaworks-tool** or skills. |

At startup, the merged map above is passed to `ToolHandler`, so common and personal tools placed **before process startup** are available from the start via `use_tool` / `ExternalToolDispatcher`. Only `.py` added **during the session** requires a rescan via `refresh_tools`; otherwise, `use_tool` will not recognize the tool name (because the map has not been updated).## Procedure### Step 1: Tool Design

1. Decide on the tool name (module name) (snake_case, e.g., `my_api_tool`). It will be the first argument of `animaworks-tool my_api_tool …`.
2. Decide on the **action** (subcommand). The schema name should generally be **`{tool_name}_{action}`** (e.g., `myapi_query`). For `use_tool`, use `tool_name="myapi"`, `action="query"`.
3. Define parameters using JSON Schema (`input_schema` or `parameters`).### Step 2: Creating the module file#### Single Action Example

```python
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_tool_schemas() -> list[dict]:
    """ツールスキーマを返す。個人・共有ツールでは必須推奨（スキーマ読み込み・ログ用）。"""
    return [
        {
            "name": "my_tool_action",
            "description": "このツールが何をするかの説明",
            "input_schema": {
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "string",
                        "description": "パラメータの説明",
                    },
                    "param2": {
                        "type": "integer",
                        "description": "オプションパラメータ",
                        "default": 10,
                    },
                },
                "required": ["param1"],
            },
        }
    ]


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """スキーマ名に応じた処理を実行する（推奨）。"""
    args.pop("anima_dir", None)  # フレームワークから注入。必要なら Path(anima_dir) で利用
    if name == "my_tool_action":
        return _do_action(
            param1=args["param1"],
            param2=args.get("param2", 10),
        )
    raise ValueError(f"Unknown tool: {name}")


def _do_action(param1: str, param2: int = 10) -> dict[str, Any]:
    return {"result": f"Processed {param1} with {param2}"}
```

When starting from `animaworks-tool`, **be sure to implement `cli_main`** next (see the "`cli_main`" section below).#### Multiple Actions + Authentication (API Integration)

The resolution order for `get_credential(credential_name, tool_name, key_name="api_key", env_var=...)` is **`config.json`'s `credentials.{credential_name}`** (`api_key` or `keys[key_name]`) → **`vault.json`'s `shared` section** (key name is the string passed as argument `env_var`) → **`shared/credentials.json` (legacy, key is `env_var`)** → **environment variable `env_var`** (`core/integrations/_base.py`).

```python
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_tool_schemas() -> list[dict]:
    return [
        {
            "name": "myapi_query",
            "description": "APIにクエリを送信して結果を取得する",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "検索クエリ"},
                    "limit": {"type": "integer", "description": "最大件数", "default": 10},
                },
                "required": ["query"],
            },
        },
        {
            "name": "myapi_post",
            "description": "APIにデータを送信する",
            "input_schema": {
                "type": "object",
                "properties": {
                    "data": {"type": "string", "description": "送信データ"},
                },
                "required": ["data"],
            },
        },
    ]


class MyAPIClient:
    def __init__(self) -> None:
        from core.integrations._base import get_credential

        self._api_key = get_credential(
            "myapi",
            "myapi_tool",
            env_var="MYAPI_KEY",
        )

    def query(self, query: str, limit: int = 10) -> list[dict]:
        import httpx

        resp = httpx.get(
            "https://api.example.com/search",
            params={"q": query, "limit": limit},
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["results"]

    def post(self, data: str) -> dict:
        import httpx

        resp = httpx.post(
            "https://api.example.com/data",
            json={"data": data},
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()


def dispatch(name: str, args: dict[str, Any]) -> Any:
    args.pop("anima_dir", None)
    client = MyAPIClient()
    if name == "myapi_query":
        return client.query(query=args["query"], limit=args.get("limit", 10))
    if name == "myapi_post":
        return client.post(data=args["data"])
    raise ValueError(f"Unknown tool: {name}")
```

**Per-Anima authentication** (Chatwork, etc.): There is a pattern where the Anima name is taken from `args.get("anima_dir")` and an **Anima-specific key** like `CHATWORK_API_TOKEN__{anima_name}` is resolved via `resolve_env_style_credential(...)` (e.g., `core/integrations/_chatwork_identity.py`'s `resolve_identity`. If not registered, raise an error without falling back). The same key naming can be used in custom tools.#### `cli_main` (for animaworks-tool)

`animaworks-tool <tool_name> …` requires **`cli_main` in the module for CLI execution** across core, common, and personal modules (`core/integrations/__init__.py`'s `cli_dispatch`). The common pattern is to parse subcommands with `argparse` and call `dispatch(f"{tool}_{action}", args_dict)` internally. If you want to generate usage from a schema, also refer to `core/integrations/_base.py`'s `auto_cli_guide`.### Step 3: Saving the File

Personal tools:

```
write_memory_file(path="tools/my_tool.py", content=<コード>)
```

`tool_creation.personal` is permitted.### Step 4: Enabling Tools (Hot Reload)

Only when `tools/*.py` or `common_tools/*.py` are added or changed **after** process startup:

```
refresh_tools()
```

The file-based map of `ExternalToolDispatcher` within the same session is rescanned, and new module names are resolved from `use_tool` (files that existed before startup are typically not required).### Step 5: Sharing (Optional)

```
share_tool(tool_name="my_tool")
```

`~/.animaworks/common_tools/` is copied to. `tool_creation.shared` is required. Other Anima instances each require `refresh_tools` (or automatic discovery at startup).## Required Interface

| Function / Constant | Required | Description |
|-------------|------|-------------|
| `get_tool_schemas()` | **Strongly recommended** for personal and shared use | Used for schema loading and guide generation. The core also has modules with empty lists (e.g., `web_search` is `[]`). **Important**: `ExternalToolDispatcher.dispatch` (the path where the schema name is passed directly via `tool_use`) only matches modules for schemas **included in the `get_tool_schemas()` `name` list** for the core. Empty modules are not hit on the core side via that path. On the other hand, **`use_tool`** directly imports the module from `TOOL_MODULES` and calls `dispatch`, so **even if the schema list is empty, it can run as long as `dispatch` exists**. Custom tools should be aware of both paths; defining the schema is usually the safe choice. |
| `dispatch(name, args)` | **Recommended** | `ExternalToolDispatcher._call_module` is used preferentially. |
| Function with the same name as the schema | Alternative | Used when `dispatch` is not available, as `getattr(mod, name)(**args)`. |
| `cli_main(argv)` | **Required when using the CLI** | `animaworks-tool` entry. |
| `EXECUTION_PROFILE` | Optional | `expected_seconds`, `background_eligible`; for core tools, **`gated: True`** can require an allowlist for send-related operations (`core/tooling/permissions.py`). |## Invocation and Schema Names

- **`use_tool`**: Passed to the module's `dispatch` (or a function of the same name) via `schema_name = f"{tool_name}_{action}"`. Permission determination is **core**: `tool_registry` (that `tool_name` is included in the result of `get_permitted_tools`), **file-based (common/individual)**: that `tool_name` exists in the merged `_personal_tools` (`_handle_use_tool` of `core/tooling/handler.py`).
- **`animaworks-tool`**: If the first token is `submit`, it is a background submission (see below). **Core** imports from `TOOL_MODULES` and performs `cli_main`; **common/individual** loads from a file and performs `cli_main`. An unknown first argument may fall back to the main CLI (`animaworks`) (`_MAIN_CLI_COMMANDS` / `_ANIMA_SUBCOMMANDS` of `core/integrations/__init__.py`).
- **Gated subcommands (core only)**: If `"gated": True` is present in the corresponding action of `EXECUTION_PROFILE`, and **`{tool_name}_{action}`** (e.g., `gmail_send`) is not included in the permission set of `permissions`, the command is blocked in both the CLI and dispatch. **File-based individual and shared tools** are not in `TOOL_MODULES`, so they are not subject to this gating mechanism.## Schema Normalization

`core/tooling/schemas/loader.py` receives `_normalise_schema` / `input_schema` from `parameters`, and in the internal representation, it is unified into `parameters`.## permissions (tool_creation・external tool)

- **Loading**: `load_permissions(anima_dir)` (`core/config/schemas.py`). **`permissions.json` takes precedence**. Only when absent, parse `permissions.md` to generate and migrate JSON (`migrate_permissions_md_to_json`).
- **Tool creation** (JSON example):

```json
{
  "version": 1,
  "tool_creation": {
    "personal": true,
    "shared": false
  }
}
```

The Markdown "Tool Creation" section (lines `個人ツール` / `共有ツール`) will also have the same structure after migration.

- **External tools (core)**: `external_tools` collects the **module names of core `TOOL_MODULES`** via `get_permitted_tools`, along with the **`{tool}_{action}`** string for gate release (e.g., `gmail_send`). In `use_tool`, core tools use names included in this set on the `tool_registry` side, and **personal/shared tools** are executed even outside the core set if their names appear in **`_personal_tools` after startup merge or `refresh_tools`** (files with the same name as core tools are skipped during discovery, so no conflicts occur).## EXECUTION_PROFILE

- **`background_eligible: True`**: JSON is written to `animaworks-tool submit <tool> <subcommand> …` via `state/background_tasks/pending/`, and `PendingTaskExecutor` picks it up (`_handle_submit` of `core/integrations/__init__.py`). Profile references are only applied to **importable core modules** (file tools are less likely to be flagged as warnings at submit time).
- **`gated: True`**: For the corresponding actions of core tools, explicit permission for `tool_action` is required in permissions.

```python
EXECUTION_PROFILE: dict[str, dict[str, object]] = {
    "pipeline": {"expected_seconds": 1800, "background_eligible": True},
    "send": {"expected_seconds": 15, "background_eligible": False, "gated": True},
}
```
## Adding Core Tools to the Repository

1. Add `core/integrations/{name}.py` (items starting with `_` are excluded from scanning).
2. `TOOL_MODULES` is automatically registered via `discover_core_tools()`. No manual list is needed for `core/integrations/__init__.py`.
3. Only `_EXPOSED_TOOL_NAMES` of `core/mcp/server.py` are listed in **Mode S (MCP)** (curated). Examples as of 2026-03: `search_memory`, `read_memory_file`, `write_memory_file`, `archive_memory_file`, `send_message`, `post_channel`, `call_human`, `delegate_task`, `submit_tasks`, `update_task`, `create_skill`. **External service core tools such as Slack / Gmail / `web_search` do not appear in MCP** — they typically go through **`use_tool` / Bash (`animaworks-tool`) / skills**.
4. Add tests to `tests/`. If schemas or reference documents are auto-generated, also check the targets for `scripts/generate_reference.py`.
5. For destructive operations, consider updating `gated: True` and the permissions-side description.## Validation Checklist

- [ ] File name: snake_case, `.py`, no leading `_` (to include in scan targets)
- [ ] Prefix with `from __future__ import annotations` (project convention)
- [ ] `get_tool_schemas()` returns the correct schema name (personal and shared)
- [ ] Process all schemas with `dispatch` or a schema name function
- [ ] If not using `anima_dir`, avoid side effects with `args.pop("anima_dir", None)`
- [ ] Implement `cli_main` and verify operation with `animaworks-tool`
- [ ] Attach `timeout=` for external HTTP
- [ ] Use `get_credential` for authentication (or per-anima resolution of the same type as core)
- [ ] `logging.getLogger(__name__)` is recommended for logs## Security

1. Do not embed confidential information in code. Use `get_credential` / vault / config.
2. Do not touch other Anima directories.
3. In the core, design "write / send" operations together with `gated` and permissions.## Reference Implementations

- Thin entry + `_client` / `_cli` split: `core/integrations/chatwork.py`, `slack.py`, `discord.py`
- Authentication and API: `core/integrations/gmail.py`, `github.py`, `notion.py`, `google_calendar.py`, `google_tasks.py`
- Long-running and pipeline: `core/integrations/image_gen.py` (facade, `image/` subpackage + `EXECUTION_PROFILE`)
- Search and local LLM: `core/integrations/web_search.py` (if `get_tool_schemas` is empty, it does not match in `ExternalToolDispatcher.dispatch`'s core path. `use_tool` is possible with `dispatch`), `x_search.py`, `local_llm.py`
- Dispatcher and CLI entry: `core/tooling/dispatch.py`, `core/integrations/__init__.py` (`cli_dispatch` / `_handle_submit`)
## Notes

- Tools are executable Python. They are distinct from skills (Markdown).
- Only tools added **after startup** require **`refresh_tools`** (files that exist before startup are already scanned at startup).
- Personal and shared files with the same name as core files are not adopted.