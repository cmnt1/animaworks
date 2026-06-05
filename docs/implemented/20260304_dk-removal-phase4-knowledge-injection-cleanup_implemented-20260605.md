# DK段階廃止 Phase 4: Knowledge 全文注入停止・DKコードクリーンアップ

## Overview

`build_system_prompt()` での Knowledge 全文注入を停止し、DK（Distilled Knowledge）注入に関連するコードパス全体をクリーンアップする。DK段階廃止の最終フェーズ。

**前提**: Phase 3（Procedures全文注入停止）の運用観察を完了し、応答品質に劣化がないことを確認済みであること。

**依存**: `docs/issues/20260304_dk-removal-phase3-procedures-injection-removal.md` 完了後

## Problem / Background

### Current State (Phase 3 完了後の想定)

- Phase 1: `_compute_overflow_files()` は `None` 固定済み（Channel C全検索化済み）
- Phase 2: `_BUDGET_RELATED_KNOWLEDGE` は1200に拡大済み
- Phase 3: Procedures全文注入は停止済み
- Knowledge注入ブロックがDKバジェット内で全文注入を継続: `core/prompt/builder.py:797-813`
- `overflow_files` パラメータが `_compute_overflow_files()` → `_run_priming()` → `prime_memories()` → Channel C と伝搬するコードパスが残存
- `BuildResult.overflow_files`, `BuildResult.injected_knowledge_files`, `BuildResult.injected_procedures` フィールドが未使用状態

### Root Cause

Phase 1-3 で機能は段階的に無効化されたが、コード上のデッドパスが残っている。Knowledge全文注入を停止し、関連コードを整理することで保守性を回復する。

## Decided Approach / 確定方針

### Design Decision

2段階で実施:
1. Knowledge全文注入を停止（Procedures同様、overflow_filesに全件追加）
2. DK関連のデッドコードをクリーンアップ

### Changes by Module

#### Step 1: Knowledge全文注入停止

##### `core/prompt/builder.py`

**変更箇所**: L755-813 DK注入ブロック全体

```python
# Before (L755-813) — Phase 3完了後の状態
# ── Distilled Knowledge Injection (skip for task) ─────
injected_knowledge_files: list[str] = []
injected_procedures: list[Path] = []
overflow_files: list[str] = []

if is_task:
    knowledge_budget = 0
elif tier == TIER_FULL:
    ...
    knowledge_budget = min(int(ctx_window * 0.05), 4000)
elif tier == TIER_STANDARD:
    knowledge_budget = min(int(context_window * 0.03), 2000)
else:
    knowledge_budget = 0

procedures_list, knowledge_list = memory.collect_distilled_knowledge_separated()
used_tokens = 0

# (Phase 3で無効化済みのProceduresブロック)
for entry in procedures_list:
    overflow_files.append(entry["name"])

know_parts: list[str] = []
for entry in knowledge_list:
    est_tokens = len(entry["content"]) // 3
    if used_tokens + est_tokens <= knowledge_budget:
        know_parts.append(...)
        ...
    else:
        overflow_files.append(entry["name"])

# After — DK注入ブロック全体を削除
# (DK injection removed — knowledge is accessed via Channel C RAG search
#  and skill tool Progressive Disclosure.
#  See: docs/issues/20260304_dk-removal-phase4-*.md)
```

#### Step 2: デッドコードクリーンアップ

##### `core/prompt/builder.py`

- `BuildResult` dataclass から `injected_procedures`, `injected_knowledge_files`, `overflow_files` フィールドを削除
- `collect_distilled_knowledge_separated()` の呼び出しを削除
- `knowledge_budget` 計算ロジック全体を削除
- `build_system_prompt()` の戻り値を `BuildResult(system_prompt=prompt)` に簡素化

##### `core/_agent_priming.py`

- `_compute_overflow_files()` メソッドを削除（Phase 1で`return None`化済み）
- `_run_priming()` の `overflow_files` パラメータを削除

##### `core/_agent_cycle.py`

- `overflow_files = self._compute_overflow_files()` 呼び出しを削除（L143, L540）
- `_run_priming()` への `overflow_files=overflow_files` 引数を削除（L148, L545）

##### `core/memory/priming.py`

- `prime_memories()` の `overflow_files` パラメータを削除
- Channel Cの3モード分岐（L189-206）を単一パス（常に全検索）に簡素化:

```python
# Before (L189-206)
if overflow_files is None:
    channel_c_coro = self._channel_c_related_knowledge(
        keywords, message=message,
    )
elif overflow_files:
    channel_c_coro = self._channel_c_related_knowledge(
        keywords, restrict_to=overflow_files, message=message,
    )
else:
    async def _noop() -> tuple[str, str]:
        return ("", "")
    channel_c_coro = _noop()

# After
channel_c_coro = self._channel_c_related_knowledge(
    keywords, message=message,
)
```

- `_channel_c_related_knowledge()` の `restrict_to` パラメータを削除（全検索のみ）

##### `core/memory/manager.py`

- `collect_distilled_knowledge()` メソッドは他で使われていなければ削除候補（要確認）
- `collect_distilled_knowledge_separated()` 同上

### Rejected Alternatives

| Approach | Verdict | Reason |
|----------|---------|--------|
| Knowledge注入を残してProceduresのみ廃止 | **Rejected** | knowledgeもChannel CのRAG検索でカバー可能。中途半端な状態はコードの複雑さを維持してしまう |
| クリーンアップを別Issueに分離 | **Rejected** | Knowledge停止とクリーンアップは論理的に一体。同一Issueで完結させる方がコンテキスト管理が容易 |

### Edge Cases

| Case | Handling |
|------|----------|
| `collect_distilled_knowledge*` が他で使われている場合 | grep確認の上、使用箇所があれば残す。なければ削除 |
| `BuildResult` のフィールド削除で既存コードが参照している場合 | grep確認の上、参照箇所を修正 |
| テストが `overflow_files` や `injected_procedures` をアサートしている | テストを更新 |

### Out of Scope

- Channel Cのキーワード抽出アルゴリズム改善
- Primingバジェット全体の再設計
- knowledge/proceduresディレクトリ自体の廃止（ファイルは残す。RAGインデックス対象として引き続き使用）

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Knowledge全文がなくなり応答品質低下 | Low | Medium | Phase 1-3で段階的にDK依存を減らしているため、Phase 4時点での影響は最小。Channel Cが代替済み |
| デッドコード削除で見落としたコードパスが壊れる | Low | Medium | grep で全参照箇所を確認。テスト全通過を確認 |
| `collect_distilled_knowledge*` の他用途がある | Low | Low | 使用箇所確認の上で判断 |

## Implementation Plan

### Step 1: Knowledge全文注入停止

1. `builder.py` のKnowledge注入ブロックを無効化
2. 統合確認: Anima応答が正常であること
3. 1週間の観察

### Step 2: デッドコードクリーンアップ

1. `BuildResult` フィールド削除
2. `_compute_overflow_files()` 削除
3. `overflow_files` パラメータを全コードパスから削除
4. `prime_memories()` のChannel C分岐を単一パスに簡素化
5. `_channel_c_related_knowledge()` の `restrict_to` パラメータ削除
6. `collect_distilled_knowledge*` メソッドの使用箇所確認→不要なら削除
7. 既存テスト更新・全通過確認

### Completion Condition

- `builder.py` のDK注入ロジック全体が削除済み
- `overflow_files` 関連のコードパスが全て除去済み
- Channel Cが単一パス（全検索）で動作
- `BuildResult` がシンプルな `system_prompt` のみのdataclass
- 既存テストが全通過（テスト自体も更新済み）
- Animaの応答品質に劣化がないこと

## Code References

- `core/prompt/builder.py:71-111` — `BuildResult` dataclass（フィールド削除対象）
- `core/prompt/builder.py:755-813` — DK注入ブロック全体（削除対象）
- `core/prompt/builder.py:966-971` — `BuildResult` 返却箇所（簡素化対象）
- `core/_agent_priming.py:28-58` — `_compute_overflow_files()`（削除対象）
- `core/_agent_priming.py:60-127` — `_run_priming()`（overflow_files引数削除）
- `core/_agent_cycle.py:143-149` — overflow計算→priming呼び出し（削除対象）
- `core/_agent_cycle.py:540-546` — ストリーミング版同等箇所（削除対象）
- `core/memory/priming.py:150-206` — `prime_memories()`（overflow_files引数削除、Channel C簡素化）
- `core/memory/manager.py` — `collect_distilled_knowledge()`, `collect_distilled_knowledge_separated()`（削除候補）
