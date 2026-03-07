---
gh_issue: 15
---

# 汎用 Notion 外部ツール — PR #2 ベースのクリーンアップ実装

## Overview

AnimaWorks の外部ツールとして汎用 Notion API クライアントを追加する。PR #2（`feat: Notion FB一覧DB作成 + URLバグ修正`）の `NotionClient` コアを抽出・クリーンアップし、ドメイン固有コードを除去した上で、既存の Slack/Chatwork/Gmail ツールと同じパターンで `core/tools/notion.py` を実装する。

## Problem / Background

### Current State

- AnimaWorks には Slack、Chatwork、Gmail、GitHub 等の外部ツールがあるが、Notion ツールが存在しない
- PR #2 で Notion ツールが提出されたが、ドメイン固有ロジック（FB一覧DB、STATUS_CATEGORIES、DEFAULT_DATABASE_ID）が混在しており、そのままでは汎用フレームワークに取り込めない
- PR #2 は CLOSED（未マージ）状態

### Root Cause

1. PR #2 が特定組織のワークフローに密結合 — `core/tools/notion.py` に `FB_DB_SCHEMA`、`STATUS_CATEGORIES` 等がハードコード
2. `get_credential` の引数順序バグ — `get_credential("notion", "integration_token", ...)` は `tool_name` に `"integration_token"` を渡している
3. i18n 未対応 — ユーザー向け文字列がハードコード日本語

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/tools/notion.py` | Direct | 新規作成 |
| `core/i18n.py` | Direct | Notion ツール用 i18n 文字列追加 |
| `tests/unit/core/tools/test_notion.py` | Direct | 新規テスト |
| 既存ツール | No change | 影響なし（独立モジュール） |

## Decided Approach / 確定方針

### Design Decision

確定: PR #2 の `NotionClient` コア（CRUD/バッチ/リトライ/例外階層）をベースに、ドメイン固有コードを完全除去してクリーンアップする。APIバージョンは安定版 `2022-06-28` を使用。`get_page_content` は blocks JSON を Markdown に変換して返す。既存の外部ツールパターン（`EXECUTION_PROFILE` / `dispatch()` / `cli_main()` / `get_tool_schemas()` / `get_cli_guide()`）に完全準拠する。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| A: ゼロから書き直し | 設計の自由度 | PR #2 の品質良いリトライ/例外/CRUD を再実装する無駄 | **Rejected**: 既存コードの流用が効率的 |
| B: API v2025-09-03 使用 | data_source 対応 | 既存ワークスペースとの互換性リスク、普及途上 | **Rejected**: 安定版で十分、v2 で移行可能 |
| C: blocks JSON そのまま返す | API 忠実 | LLM エージェントに可読性が低い | **Rejected**: Markdown 変換の方がエージェント体験が良い |
| D: PR #2 のドメイン固有ツール含める | PR の変更量削減 | フレームワークコアに業務ロジックが混入 | **Rejected**: 汎用性を損なう |

### Key Decisions from Discussion

1. **APIバージョン `2022-06-28`**: 安定版を使用 — Reason: 広く使われており互換性リスクが低い
2. **PR #2 ベースクリーンアップ**: NotionClient のリトライ・例外・CRUD を流用 — Reason: 品質の良い実装が既にある
3. **Markdown 変換**: `get_page_content` は blocks → Markdown — Reason: エージェントの可読性重視
4. **vault 認証解決**: `NOTION_API_TOKEN` / `NOTION_API_TOKEN__{anima_name}` — Reason: 既存ツールと同じパターン

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/tools/notion.py` | New | NotionClient + 8 サブコマンド + CLI + dispatch |
| `core/i18n.py` | Modify | `notion.*` キーで i18n 文字列追加 |
| `tests/unit/core/tools/test_notion.py` | New | 全サブコマンド + NotionClient のユニットテスト |

### Edge Cases

| Case | Handling |
|------|----------|
| ページ ID ハイフン付き/なし | 内部で `replace("-", "")` 正規化 |
| ペイロード 500KB 超過 | `ValueError` + 明確なエラーメッセージ |
| 429 レート制限 | `retry_on_rate_limit` で `Retry-After` ヘッダー尊重、最大 5 回リトライ |
| 5xx サーバーエラー | リトライ対象に含める |
| 認証トークン未設定 | `ToolConfigError` で設定方法を案内 |
| 未対応ブロックタイプ | Markdown 変換時にプレーンテキストフォールバック |
| ページネーション | `page_size`（デフォルト 10、最大 100）+ `start_cursor` サポート |
| 空のクエリ結果 | 空リスト返却（エラーではない） |

## Implementation Plan

### Phase 1: NotionClient コア

| # | Task | Target |
|---|------|--------|
| 1-1 | NotionClient クラス作成（httpx、認証、ヘッダー） | `core/tools/notion.py` |
| 1-2 | 例外階層（NotionAPIError, RateLimitError, ServerError） | `core/tools/notion.py` |
| 1-3 | `_request()` メソッド（リトライ統合、ペイロード検証） | `core/tools/notion.py` |
| 1-4 | CRUD メソッド（create_page, get_page, update_page, query_database, get_database） | `core/tools/notion.py` |
| 1-5 | create_database メソッド | `core/tools/notion.py` |
| 1-6 | search メソッド | `core/tools/notion.py` |
| 1-7 | blocks → Markdown 変換（get_page_content） | `core/tools/notion.py` |

**Completion condition**: NotionClient の全メソッドが httpx モックで正しく動作する

### Phase 2: ツールインターフェース

| # | Task | Target |
|---|------|--------|
| 2-1 | EXECUTION_PROFILE 定義 | `core/tools/notion.py` |
| 2-2 | dispatch() ルーティング（8 サブコマンド） | `core/tools/notion.py` |
| 2-3 | get_tool_schemas() / get_cli_guide() | `core/tools/notion.py` |
| 2-4 | cli_main() argparse CLI | `core/tools/notion.py` |
| 2-5 | build_page_url() ユーティリティ | `core/tools/notion.py` |

**Completion condition**: `animaworks-tool notion --help` が正しく表示され、dispatch が全サブコマンドをルーティング

### Phase 3: i18n + テスト

| # | Task | Target |
|---|------|--------|
| 3-1 | i18n 文字列登録（エラーメッセージ、CLI ヘルプ） | `core/i18n.py` |
| 3-2 | NotionClient ユニットテスト | `tests/unit/core/tools/test_notion.py` |
| 3-3 | dispatch ルーティングテスト | `tests/unit/core/tools/test_notion.py` |
| 3-4 | blocks → Markdown 変換テスト | `tests/unit/core/tools/test_notion.py` |
| 3-5 | エッジケーステスト（認証なし、429、5xx、ペイロード超過） | `tests/unit/core/tools/test_notion.py` |
| 3-6 | 既存テスト全パス確認 | `tests/unit/` |

**Completion condition**: カバレッジ 80% 以上、既存テスト全パス、ruff クリーン

## Scope

### In Scope

- NotionClient（CRUD + search + create_database）
- 8 サブコマンド: search, get_page, get_page_content, get_database, query, create_page, update_page, create_database
- blocks → Markdown 変換
- レート制限リトライ
- Per-Anima / 共有の認証情報解決
- i18n 対応
- ユニットテスト（80%+ カバレッジ）

### Out of Scope

- `append_blocks`（ブロック追加） — Reason: v1.1 で追加検討
- `trash_page`（ソフト削除） — Reason: v1.1 で追加検討
- Comments API — Reason: エージェントワークフローでの需要が低い
- OAuth / Public integration — Reason: Internal integration で十分
- `data_source` 系エンドポイント（API v2025-09-03） — Reason: 普及途上、v2 で移行
- common_skills テンプレート（notion-tool スキル） — Reason: 別 Issue で対応
- バッチ操作（batch_create_pages） — Reason: v1 では単一操作に集中

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Notion API 仕様変更 | API 呼び出し失敗 | API_VERSION 定数で一元管理、ヘッダーで明示指定 |
| httpx 依存追加 | 依存ツリー拡大 | httpx は既に PR #2 で使用実績あり。他ツール（slack.py 等）も httpx 使用 |
| blocks → Markdown 変換の品質 | 未対応ブロックで情報欠落 | 主要ブロックタイプ（heading, paragraph, list, code, quote, table, toggle, callout, divider, image, bookmark, link_preview）をカバー。未対応はプレーンテキストフォールバック |

## Acceptance Criteria

- [ ] `core/tools/notion.py` が自動検出され `animaworks-tool notion` で CLI 利用可能
- [ ] 8 サブコマンド（search, get_page, get_page_content, get_database, query, create_page, update_page, create_database）が動作
- [ ] `get_page_content` が Markdown 形式で返す
- [ ] レート制限リトライが正しく動作（429 → Retry-After 尊重）
- [ ] Per-Anima / 共有の認証情報解決が正しく動作
- [ ] ドメイン固有コードが一切含まれない（FB_DB_SCHEMA、STATUS_CATEGORIES、DEFAULT_DATABASE_ID なし）
- [ ] ユーザー向け文字列が `t()` 経由
- [ ] ユニットテストのカバレッジ 80% 以上
- [ ] 既存テスト全パス（リグレッションなし）
- [ ] ruff check / ruff format クリーン

## References

- PR #2 diff: `gh pr diff 2 --repo xuiltul/animaworks` — ベースコード
- `core/tools/slack.py` — 外部ツールパターンの参照実装
- `core/tools/_base.py` — `get_credential()`, `ToolResult`, `logger`
- `core/tools/_retry.py` — `retry_on_rate_limit()`
- Notion API docs: https://developers.notion.com/reference
