# エピソード→手続きの自動蒸留 — 日次固定化での振り分け + 繰り返しパターン検出

## Overview

日次固定化パイプラインを拡張し、エピソードから手続き的な内容をknowledge/ではなくprocedures/に自動振り分けする。加えて、週次統合時に繰り返しパターンを検出し、反復実行された手順を手順書として自動蒸留する。`20260218_procedural-memory-foundation.md`（基盤整備）の完了を前提とする。

## Problem / Background

### Current State

- 日次固定化（`_summarize_episodes()`）はエピソードから抽出した内容を**すべてknowledge/に格納**する — `core/memory/consolidation.py:288-323`
- プロンプト（L311-312）には「手順・ワークフロー・プロセスの記録」を抽出対象として明記しているが、出力先はknowledge/のみ
- 手続き記憶は**エージェントの意図的記銘のみ**で作成される。エピソードから手順を自動抽出するパスが存在しない
- エージェントが「これは手順として保存すべき」と自律的に判断しない限り、有用なワークフローが記憶されない

### Root Cause

1. **固定化プロンプトの出力先がknowledge/のみ**: `_summarize_episodes()` のプロンプトが `knowledge/xxx.md` への出力のみ指示しており、`procedures/` への振り分けが設計されていない — `core/memory/consolidation.py:311-323`
2. **繰り返しパターン検出の不在**: 同じタイプのタスクを何度も実行しても、その共通手順が自動的に抽出される仕組みがない

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/memory/consolidation.py` | Direct | 日次固定化プロンプト拡張、procedures/への書き込みパス追加、週次パターン検出 |
| `core/memory/manager.py` | Direct | procedures/への自動書き込み（frontmatter付き） |
| `core/memory/activity.py` | Indirect | パターン検出のデータソース |

## Decided Approach / 確定方針

### Design Decision

確定: **2経路の組み合わせ**。(1) 日次固定化でLLMがエピソード内容をknowledge/procedures/skipに振り分ける、(2) 週次統合時に繰り返しパターン検出（activity_logから類似タスク3回以上成功を検出）で手順書を自動蒸留する。両経路で生成されたproceduresは既存procedures/skillsとの重複チェックを経てから保存する。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| 日次固定化での振り分けのみ | 毎日の固定化に組み込むだけ | 繰り返しパターンの検出ができない。1回限りの手順的エピソードと反復的ワークフローの区別がつかない | **Rejected**: 繰り返しパターンの蒸留が欠落 |
| 繰り返しパターン検出のみ | 確実に反復されたパターンのみ抽出 | 1回でも有用な手順（トラブルシューティング等）が拾えない | **Rejected**: 即時的な手順蒸留が欠落 |
| **両方の組み合わせ (Adopted)** | 即時振り分け + 反復パターン蒸留 | 実装量が多い | **Adopted**: 手順的内容の即時捕捉と反復ワークフローの自動蒸留を両立 |

### Key Decisions from Discussion

1. **日次固定化の振り分け**: LLMプロンプトを拡張し、抽出内容を`knowledge/`（教訓・方針・事実）と`procedures/`（手順・ワークフロー・チェックリスト）に振り分ける。LLMが「手続き的」と判断した内容はprocedures/に出力
2. **パターン検出のトリガー**: 週次統合時にactivity_logから類似タスクの反復実行（3回以上成功）を検出。ベクトル類似度で同一タイプのタスクをクラスタリング
3. **自動蒸留のconfidence**: 自動生成されたproceduresはconfidence=0.4（低め）でスタート。成功報告で上昇
4. **重複チェック**: RAGで既存procedures/skillsとの類似度を検索。類似度0.85以上なら新規作成せずマージ候補としてフラグ

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/memory/consolidation.py` | Modify | 日次固定化プロンプト拡張（knowledge/procedures振り分け）、`_merge_to_procedures()`追加、週次パターン検出 |
| `core/memory/manager.py` | Modify | procedures/への自動書き込み（frontmatter付き） |

#### Change 1: 日次固定化プロンプト拡張

**Target**: `core/memory/consolidation.py` — `_summarize_episodes()`

```
# Before: knowledge/への出力のみ
出力形式:
## 既存ファイル更新
- ファイル名: knowledge/xxx.md
  追加内容: ...

## 新規ファイル作成
- ファイル名: knowledge/yyy.md
  内容: ...

# After: knowledge/ + procedures/ への振り分け
各エピソードの内容を以下の基準で分類してください:

- **knowledge/**: 教訓、方針、事実、パターン認識、原則（「なぜ」「何が」の知識）
- **procedures/**: 手順、ワークフロー、チェックリスト、作業フロー、手順書（「どうやるか」の手順）

出力形式:
## 既存ファイル更新
- ファイル名: knowledge/xxx.md（または procedures/xxx.md）
  追加内容: ...

## 新規knowledge作成
- ファイル名: knowledge/yyy.md
  内容: ...

## 新規procedure作成
- ファイル名: procedures/zzz.md
  description: この手順の概要（1行）
  内容: ...
```

#### Change 2: 週次パターン検出

**Target**: `core/memory/consolidation.py` — `weekly_integrate()`

```python
async def _detect_repeated_patterns(self) -> list[dict]:
    """activity_logから繰り返しタスクパターンを検出し、手順書を蒸留する"""
    # 1. 過去7日のactivity_logからtool_useとresponse_sentイベントを収集
    # 2. ベクトル類似度で類似タスクをクラスタリング（min_similarity=0.80）
    # 3. 3回以上成功したクラスタを抽出
    # 4. 各クラスタについてLLMで共通手順を蒸留
    # 5. 既存procedures/skillsとの重複チェック（RAG類似度0.85以上→マージ候補）
    # 6. 新規procedureとして保存（confidence=0.4）
```

### Edge Cases

| Case | Handling |
|------|----------|
| LLMがknowledge/procedures振り分けを誤る場合 | procedures/に格納された知識的内容は次回の日次固定化で再分類可能。致命的ではない |
| パターン検出で誤った類似クラスタが形成される場合 | 蒸留されたprocedureはconfidence=0.4でスタートし、使用されなければ効用ベース忘却（Issue 6）で自然消滅 |
| 既存procedureと重複する蒸留結果の場合 | RAG重複チェックで検出し、新規作成せずwarningログ。将来的にはマージ提案 |
| エピソードが手順的内容を含まない日 | procedures/への出力が0件。正常動作 |
| パターン検出でactivity_logが空の場合 | パターン検出をスキップ |

## Implementation Plan

### Phase 1: 日次固定化の振り分け

| # | Task | Target |
|---|------|--------|
| 1-1 | `_summarize_episodes()` プロンプト拡張（knowledge/procedures振り分け） | `core/memory/consolidation.py` |
| 1-2 | `_merge_to_procedures()` メソッド実装（パーサー + frontmatter付き書き込み） | `core/memory/consolidation.py` |
| 1-3 | 重複チェック（RAG類似度検索）実装 | `core/memory/consolidation.py` |
| 1-4 | Phase 1のユニットテスト | `tests/` |

**Completion condition**: 日次固定化でエピソードがknowledge/とprocedures/に振り分けられる

### Phase 2: 週次パターン検出・蒸留

| # | Task | Target |
|---|------|--------|
| 2-1 | activity_logからのタスクパターンクラスタリング実装 | `core/memory/consolidation.py` |
| 2-2 | LLMによる共通手順蒸留プロンプト実装 | `core/memory/consolidation.py` |
| 2-3 | `weekly_integrate()` へのパターン検出ステージ組み込み | `core/memory/consolidation.py` |
| 2-4 | Phase 2の統合テスト | `tests/` |

**Completion condition**: 週次統合で繰り返しパターンが検出され、手順書が自動蒸留される

## Scope

### In Scope

- 日次固定化プロンプトのknowledge/procedures振り分け
- procedures/への自動書き込み（frontmatter付き）
- 既存procedures/skillsとの重複チェック
- 週次パターン検出（activity_logベース）
- パターンからの手順書自動蒸留

### Out of Scope

- 手順書の品質検証（NLI検証） — 理由: knowledge/の検証（Issue 1）と同じ仕組みを将来的に適用。本Issueではconfidence=0.4のラベルで対応
- 手順の成功/失敗追跡 — 理由: Issue 3（基盤整備）で対応済み
- 手順の再固定化 — 理由: Issue 5で対応

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLMの振り分け精度が低く、知識が手順に、手順が知識に分類される | 記憶の分類品質低下 | procedures/に格納された知識的内容はRAG検索で発見可能。分類ミスは致命的ではない |
| パターン検出の偽陽性で不要な手順書が生成される | procedures/の肥大化 | confidence=0.4のラベル + 効用ベース忘却（Issue 6）で自然消滅 |
| 蒸留された手順が不正確・不完全 | エージェントが不正確な手順に従う | confidence=0.4で自動生成を明示。エージェントは低confidence手順を参考程度に扱う |

## Acceptance Criteria

- [ ] 日次固定化でエピソードがknowledge/とprocedures/に振り分けられる
- [ ] procedures/に自動生成されたファイルにYAML frontmatter（description, confidence=0.4）が付与されている
- [ ] 既存procedures/skillsとの重複がRAGで検出される（類似度0.85以上でスキップ）
- [ ] 週次統合で繰り返しパターン（3回以上成功）が検出される
- [ ] 検出されたパターンからLLMで手順書が自動蒸留される
- [ ] テストカバレッジ80%以上

## References

- `core/memory/consolidation.py:258-362` — `_summarize_episodes()` 現行プロンプト
- `core/memory/consolidation.py:311-312` — 「手順・ワークフロー」の抽出指示（knowledge/に出力）
- `core/memory/consolidation.py:364-469` — `_merge_to_knowledge()` パーサー
- `core/memory/consolidation.py:500-584` — `weekly_integrate()` 週次統合
- `core/memory/activity.py` — ActivityLogger（パターン検出のデータソース）
- `20260218_procedural-memory-foundation.md` — 前提Issue（frontmatter基盤）
- [AWM](https://arxiv.org/abs/2409.07429) — エージェントワークフロー記憶（スノーボール効果）
- [ExpeL](https://arxiv.org/abs/2308.10144) — 経験からの洞察抽出
- [Mem^p](https://arxiv.org/abs/2508.06433) — 手続き記憶の体系的探索（Build戦略）
