# 出自トラッキング Phase 5: Mode S — MCP ツール結果の trust ラベル付与

## Overview

全5フェーズの出自トラッキング導入の第5弾。Mode S（Claude Agent SDK + MCP）でのツール結果に `wrap_tool_result()` を適用し、trust 境界タグを付与する。このフェーズ完了で、セキュリティ検証 #3（Mode S ラベル欠落）が解決し、全実行モード（S/A/B）で trust ラベリングが統一される。

依存: Phase 1（基盤）。Phase 2〜4 とは独立で並行実装可能。

## Problem / Background

### Current State

- Mode A（LiteLLM）/ Mode B（Assisted）では `wrap_tool_result()` がツール結果に trust タグを付与する — `core/execution/litellm_loop.py:319`, `core/execution/assisted.py:573`
- Mode S（Agent SDK + MCP）では `core/mcp/server.py` の `call_tool()` が `handler.handle()` の生の出力をそのまま返しており、`wrap_tool_result()` を通さない — `core/mcp/server.py:498-499`

```python
# core/mcp/server.py:498-499 (現状)
result = await asyncio.to_thread(handler.handle, name, coerced_args)
return [TextContent(type="text", text=result)]  # ← trust タグなし
```

- Mode S の Anima が `web_search` や `slack_messages` 等の untrusted ツールを実行した場合、結果に trust ラベルが付かず、`tool_data_interpretation.md` のルールが機能しない

### Root Cause

MCP サーバーのツール結果パスに `wrap_tool_result()` が組み込まれていない。

### Impact

| コンポーネント | 影響 | 説明 |
|--------------|------|------|
| `core/mcp/server.py` | Direct | `call_tool()` 内で `wrap_tool_result()` を適用 |

## Decided Approach / 確定方針

### Design Decision

`core/mcp/server.py` の `call_tool()` 内で、`handler.handle()` の結果を `wrap_tool_result(name, result)` でラップしてから返す。Phase 1 の基盤が利用可能なら origin 引数も渡す。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Agent SDK 側で後処理 | MCP サーバー変更不要 | Agent SDK はフレームワーク外部、制御不能 | **Rejected**: SDK のツール結果処理フックがない |
| ToolHandler.handle() 内でラップ | 全モードで統一 | Mode A/B で二重ラップになる | **Rejected**: 既存の Mode A/B パスを壊す |

### Key Decisions from Discussion

1. **ラップ位置は MCP server.py の call_tool() 内**: `handler.handle()` の戻り値に対して `wrap_tool_result()` を適用 — 理由: Mode S 固有のパスで、他モードに影響しない
2. **エラー結果はラップしない**: JSON エラーレスポンス（`status: "error"`）は trust タグ不要 — 理由: フレームワーク生成のエラーメッセージで、外部データを含まない

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/mcp/server.py` | Modify | `call_tool()` で `wrap_tool_result()` を適用 |

#### Change 1: call_tool() にラップ追加

**Target**: `core/mcp/server.py`

```python
# Before (line 495-499)
    coerced_args = _coerce_integers(dict(arguments or {}), name)

    try:
        result = await asyncio.to_thread(handler.handle, name, coerced_args)
        return [TextContent(type="text", text=result)]

# After
    from core.execution._sanitize import wrap_tool_result

    coerced_args = _coerce_integers(dict(arguments or {}), name)

    try:
        result = await asyncio.to_thread(handler.handle, name, coerced_args)
        wrapped = wrap_tool_result(name, result)
        return [TextContent(type="text", text=wrapped)]
```

`wrap_tool_result()` は `result` が空/falsy なら元の値をそのまま返すので、空結果の場合も安全。

### Edge Cases

| Case | Handling |
|------|----------|
| ツール結果が空文字列 | `wrap_tool_result()` が元の値をそのまま返す（空チェック済み） |
| ツール実行がエラー | `except` ブロックの JSON エラーレスポンスはラップしない（既にフレームワーク生成） |
| ToolNotFound / InitError | 既存の JSON エラーレスポンスパスは変更なし |
| `_EXPOSED_NAMES` にないツール | `call_tool()` の冒頭でリジェクト（既存ガード、ラップ処理に到達しない） |
| import 失敗 | `wrap_tool_result` の import を try/except で保護し、失敗時は元の result をそのまま返す |

## Implementation Plan

### Phase 5-1: call_tool() 修正

| # | Task | Target |
|---|------|--------|
| 5-1-1 | `call_tool()` に `wrap_tool_result()` 適用 | `core/mcp/server.py` |

**Completion condition**: Mode S で `web_search` ツールの結果に `<tool_result tool="web_search" trust="untrusted">` タグが付与されること

## Scope

### In Scope

- `core/mcp/server.py` の `call_tool()` にラップ処理追加

### Out of Scope

- Mode S のセッション origin 管理（MCP サーバーはステートレスで、セッション origin の伝播は Agent SDK 側の制約）— 将来課題
- Agent SDK の PreCompact / PostCompact フックとの連携 — 別 Issue

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| 二重ラップ | trusted ツールが不必要にラップされる | `wrap_tool_result()` は全ツールに適用しても問題ない（trusted タグも正しく付与される） |
| Agent SDK が trust タグを特別扱い | 予期しない動作 | タグは XML 風テキストであり、SDK はプレーンテキストとして渡すのみ |
| import エラー | MCP サーバー起動失敗 | import を try/except で保護 |

## Acceptance Criteria

- [ ] Mode S で `web_search` ツール結果に `<tool_result tool="web_search" trust="untrusted">` タグが含まれる
- [ ] Mode S で `search_memory` ツール結果に `<tool_result tool="search_memory" trust="trusted">` タグが含まれる
- [ ] Mode S で `read_file` ツール結果に `<tool_result tool="read_file" trust="medium">` タグが含まれる
- [ ] ToolNotFound / InitError のエラーレスポンスがラップされないこと
- [ ] 空のツール結果がラップされないこと
- [ ] MCP サーバーが正常起動すること
- [ ] Mode A / Mode B の動作に影響がないこと

## References

- `core/mcp/server.py:456-514` — call_tool() 関数
- `core/mcp/server.py:498-499` — 現在のラップなしの結果返却
- `core/execution/_sanitize.py:70-84` — wrap_tool_result()
- `core/execution/litellm_loop.py:319` — Mode A でのラップ処理（参考）
- `core/execution/assisted.py:573` — Mode B でのラップ処理（参考）
- セキュリティ検証チャット — Mode S ラベル欠落の発見
