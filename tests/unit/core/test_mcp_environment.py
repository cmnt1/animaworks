"""All execution engines pass the same service environment to MCP."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.schemas import ModelConfig


@pytest.mark.parametrize("engine", ["claude", "codex", "grok", "cursor", "gemini"])
def test_every_engine_forwards_all_mcp_service_credentials(
    engine: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir = tmp_path / "animas" / engine
    anima_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    expected = {
        "ANIMAWORKS_EMBED_URL": "http://rag.test/api/internal/embed",
        "ANIMAWORKS_VECTOR_URL": "http://rag.test/api/internal/vector",
        "ANIMAWORKS_RERANK_URL": "http://rag.test/api/internal/rerank",
        "ANIMAWORKS_INTERNAL_AUTH": "anima.secret-token",
    }
    for name, value in expected.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "http://server.test:18500/")

    model_names = {
        "claude": "claude-sonnet-4-6",
        "codex": "gpt-5.4",
        "grok": "grok/grok-4.5",
        "cursor": "cursor/claude-4-sonnet",
        "gemini": "gemini/2.5-pro",
    }
    config = ModelConfig(model=model_names[engine], api_key="test-key")

    if engine == "claude":
        from core.execution.engines.claude.executor import AgentSDKExecutor

        mcp_env = AgentSDKExecutor(config, anima_dir)._build_mcp_env()
    elif engine == "codex":
        from core.execution.engines.codex.executor import CodexSDKExecutor

        mcp_env = CodexSDKExecutor(config, anima_dir)._build_mcp_env()
    elif engine == "grok":
        from core.execution.engines.grok.executor import GrokCLIExecutor

        servers = GrokCLIExecutor(config, anima_dir)._mcp_servers()
        mcp_env = {entry["name"]: entry["value"] for entry in servers[0]["env"]}
    elif engine == "cursor":
        from core.execution.engines.cursor.executor import CursorAgentExecutor

        executor = CursorAgentExecutor(config, anima_dir)
        executor._write_mcp_config()
        config_path = anima_dir / ".cursor-workspace" / ".cursor" / "mcp.json"
        mcp_env = json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]["aw"]["env"]
    else:
        from core.execution.engines.gemini.executor import GeminiCLIExecutor

        executor = GeminiCLIExecutor(config, anima_dir)
        executor._write_settings()
        config_path = anima_dir / ".gemini-workspace" / ".gemini" / "settings.json"
        mcp_env = json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]["aw"]["env"]

    assert {name: mcp_env[name] for name in expected} == expected
    assert mcp_env["ANIMAWORKS_SERVER_URL"] == "http://server.test:18500"
