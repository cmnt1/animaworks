# 知識矛盾検出・解決メカニズム — NLI+LLM判定によるsupersede/merge/coexist自動解決

## Overview

既存knowledgeと矛盾する新規知識が独立に生成・蓄積される問題に対し、日次固定化パイプラインに矛盾検出・解決ステージを追加する。NLIで矛盾候補を検出し、LLMで解決方法（supersede/merge/coexist）を判定する。本Issueは `20260218_consolidation-validation-pipeline.md`（YAMLフロントマター基盤）の完了を前提とする。

## Problem / Background

### Current State

- 日次固定化で既存knowledgeの**内容をLLMに渡していない**ため、矛盾する知識が独立ファイルとして生成される — `core/memory/consolidation.py:283-285`
- 既存ファイル更新は**append方式**のため、矛盾する記述が同一ファイル内に共存する — `core/memory/consolidation.py:411-412`
- 週次統合のマージプロンプトに「矛盾はより新しい方を採用」と記載があるが、ファイル単位のマージ時のみ。セクション間矛盾は未処理 — `core/memory/consolidation.py:693`
- 解決伝播はLLMに「解決済みに更新して」と指示するだけで、反映の検証がない。実ファイルに「未解決」が残存するケースを確認済み
- 無効化された知識を検索から除外する仕組みがなく、RAGが古い誤った知識を返す可能性がある

### Root Cause

1. **矛盾検出の不在**: 新規知識の生成時に既存知識との意味的対立を検出する仕組みがない
2. **知識の有効期限管理の不在**: 更新された知識（superseded）を明示的に無効化するメタデータ・フィルタリングがない
3. **append-only方式の限界**: 既存ファイルに追記するだけで、古い記述の修正・無効化を行わない設計

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/memory/consolidation.py` | Direct | 矛盾検出・解決ステージ追加 |
| `core/memory/validation.py` | Direct | 矛盾検出ロジック（NLI+LLM判定）追加 |
| `core/memory/manager.py` | Direct | supersedes/superseded_by/valid_until管理メソッド |
| `core/memory/rag/retriever.py` | Direct | superseded知識のフィルタリング |
| `core/memory/rag/indexer.py` | Direct | supersedes関連メタデータのChromaDB連携 |
| `core/memory/priming.py` | Indirect | 矛盾のない知識が注入されるようになり、プライミング品質向上 |

## Decided Approach / 確定方針

### Design Decision

確定: **NLI + LLM判定による3戦略自動解決**。日次固定化のバリデーション（Issue 1）後段で、新規知識とRAGで検索した類似既存知識をNLIでペア判定し、contradiction検出時にLLMで解決方法（supersede/merge/coexist）を判定する。AGM信念修正理論の最小変更原則に基づき、矛盾する最小限の既存知識のみを無効化する。無効化された知識はファイルを残しつつ、`superseded_by` + `valid_until` フロントマターフィールドで管理し、RAG検索から除外する。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| 時間減衰のみで暗黙的に解決 | 追加実装ゼロ | 古い知識が参照されなくなるまでのウィンドウが残る。誤った情報が長期間活性 | **Rejected**: 矛盾する知識が数十日間検索され続けるリスク |
| 完全削除方式 | シンプル。矛盾即解消 | AGM最小変更原則に反する。誤判定時のリカバリが不可能 | **Rejected**: トレーサビリティが失われ、誤判定時に知識喪失 |
| 人間エスカレーション | 最高精度 | 夜間バッチで完結させたい。人間介入のレイテンシ | **Rejected**: 自動化優先。高信頼度の矛盾は自動解決可能 |
| **NLI + LLM 3戦略自動解決 (Adopted)** | 高精度・自動完結・トレーサビリティ確保 | NLIモデル + LLMコスト | **Adopted**: 夜間バッチのコスト許容下で品質と自動化を両立 |

### Key Decisions from Discussion

1. **矛盾検出フロー**: 新規知識 → RAGで類似既存知識を上位5件検索 → NLIでペア判定 → contradiction時にLLMで解決方法判定
2. **解決戦略3種（supersede/merge/coexist）**: LLMが文脈に基づいて選択。時間的更新=supersede、情報の補完=merge、条件依存=coexist
3. **supersede方式**: 旧知識のファイルは残し、フロントマターの`superseded_by` + `valid_until`で無効化。RAG検索からデフォルト除外
4. **NLIモデル**: Issue 1と同じ `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` インスタンスを共有
5. **NLI contradiction閾値**: 確信度0.7以上をcontradictionとして扱う。それ以下はneutralとしてスキップ
6. **初回矛盾スキャン**: Issue 2デプロイ後の初回週次統合で、全既存knowledge間の矛盾スキャンを1回実行

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/memory/consolidation.py` | Modify | 矛盾検出・解決ステージを日次固定化パイプラインに追加。初回矛盾スキャンを週次統合に追加 |
| `core/memory/validation.py` | Modify | 矛盾検出ロジック（NLIペア判定 + LLM解決判定）を追加 |
| `core/memory/manager.py` | Modify | `supersede_knowledge()`, `read_active_knowledge()` メソッド追加 |
| `core/memory/rag/retriever.py` | Modify | `valid_until` フィルタ追加（superseded知識のデフォルト除外） |
| `core/memory/rag/indexer.py` | Modify | supersedes/superseded_by/valid_untilメタデータのChromaDB連携 |

#### Change 1: 矛盾検出・解決ステージ

**Target**: `core/memory/consolidation.py` — `daily_consolidate()`

```python
# After validation (Issue 1), before writing:
validated = await self._validate_knowledge(sanitized, episodes_text)
resolved = await self._detect_and_resolve_contradictions(validated)  # NEW
affected = await self._merge_to_knowledge(resolved)
```

#### Change 2: 矛盾検出メソッド

**Target**: `core/memory/validation.py`

```python
class ContradictionDetector:
    """既存knowledgeとの矛盾検出・解決"""

    CONTRADICTION_THRESHOLD = 0.7
    RAG_TOP_K = 5

    async def detect_and_resolve(
        self, new_items: list[dict], retriever: RAGRetriever
    ) -> list[dict]:
        """
        各new_itemについて:
        1. RAGで類似既存knowledgeを検索
        2. NLIでペア判定
        3. contradiction → LLMで解決方法判定
        4. supersede/merge/coexistの結果をitemに付与
        """
        results = []
        for item in new_items:
            similar = await retriever.search(
                item["content"], top_k=self.RAG_TOP_K,
                filter={"valid_until": None}  # 有効な知識のみ
            )
            contradictions = []
            for existing in similar:
                nli = self._nli_check(item["content"], existing["content"])
                if nli.label == "contradiction" and nli.score >= self.CONTRADICTION_THRESHOLD:
                    contradictions.append(existing)

            if contradictions:
                resolution = await self._resolve_contradictions(item, contradictions)
                item["resolution"] = resolution
            results.append(item)
        return results

    async def _resolve_contradictions(
        self, new_item: dict, contradictions: list[dict]
    ) -> list[ResolutionAction]:
        """LLMに矛盾ペアを提示し、解決方法を判定させる"""
        # LLMプロンプト: 新知識 + 各矛盾既存知識 + created_at + source_episodes
        # 出力: 各ペアについて supersede / merge / coexist を判定
        ...
```

#### Change 3: supersede管理メソッド

**Target**: `core/memory/manager.py`

```python
def supersede_knowledge(self, old_path: Path, new_path: Path) -> None:
    """旧知識を新知識で無効化する"""
    old_meta = self.read_knowledge_metadata(old_path)
    old_meta["superseded_by"] = new_path.stem
    old_meta["valid_until"] = datetime.now(UTC).isoformat()
    old_content = self.read_knowledge_content(old_path)
    self.write_knowledge_with_meta(old_path, old_content, old_meta)

    new_meta = self.read_knowledge_metadata(new_path)
    new_meta.setdefault("supersedes", []).append(old_path.stem)
    new_content = self.read_knowledge_content(new_path)
    self.write_knowledge_with_meta(new_path, new_content, new_meta)
```

#### Change 4: RAGフィルタリング

**Target**: `core/memory/rag/retriever.py`

```python
# Before: 全チャンクを検索
results = collection.query(query_embeddings=[embedding], n_results=top_k)

# After: superseded知識をデフォルト除外
where_filter = {"valid_until": {"$eq": ""}}  # valid_until未設定 = 有効
if include_superseded:
    where_filter = None  # デバッグ用: 全件検索
results = collection.query(
    query_embeddings=[embedding], n_results=top_k, where=where_filter
)
```

#### Change 5: LLM矛盾解決プロンプト

**Target**: `core/memory/validation.py` — `_resolve_contradictions()`

```
以下の新しい知識と既存の知識が矛盾しています。各ペアについて解決方法を判定してください。

【新しい知識】
作成日: {new_created_at}
ソース: {new_source_episodes}
内容:
{new_content}

【矛盾する既存知識 1】
ファイル: {existing_file}
作成日: {existing_created_at}
内容:
{existing_content}

各矛盾ペアについて、以下のいずれかを選択してください:

1. supersede — 新しい知識が古い知識を更新する（時間的な変化）
2. merge — 両方の情報を統合する（補完的な情報）
3. coexist — 条件によって異なる（文脈依存の知識）

出力形式（JSON）:
[
  {"existing_file": "xxx.md", "action": "supersede|merge|coexist", "reason": "理由"}
]
```

### Edge Cases

| Case | Handling |
|------|----------|
| 同一知識が3件以上と矛盾する場合 | 1対1ペアで順次処理。類似度の高いペアから優先処理 |
| supersede先がさらにsupersedeされた場合（チェイン） | `superseded_by` は直近の1件のみ記録。検索時は `valid_until` の有無だけで判定（チェイン追跡不要） |
| NLI False Positive（矛盾でないのに矛盾と判定） | LLM判定ステージで「矛盾ではない」と判定可能（action=none を返す）。NLI閾値0.7で精度を確保 |
| coexist判定された知識が将来的に一方が確定する場合 | 次回の固定化で再度矛盾検出され、supersedeに更新される |
| merge判定で統合文が元の2件より情報量が少ない場合 | merge前の2件は `archive/merged/` に保存（Issue 1のアーカイブ基盤を活用） |
| 初回矛盾スキャンで大量の矛盾が検出される場合 | 1回のスキャンで処理するペア数を上限20に制限。残りは次回の週次統合で処理 |
| RAG検索でsuperseded知識が返される場合（フィルタ前のレース条件） | `valid_until` チェックをアプリケーション層でも実施（二重チェック） |

## Implementation Plan

### Phase 1: 矛盾検出ロジック

| # | Task | Target |
|---|------|--------|
| 1-1 | `ContradictionDetector` クラス実装（NLIペア判定） | `core/memory/validation.py` |
| 1-2 | LLM矛盾解決プロンプト実装（supersede/merge/coexist判定） | `core/memory/validation.py` |
| 1-3 | Phase 1のユニットテスト（矛盾検出、解決判定、エッジケース） | `tests/` |

**Completion condition**: 新規知識と既存知識のペアに対してNLI矛盾検出 → LLM解決判定が単体で動作する

### Phase 2: supersede/merge/coexist実行ロジック

| # | Task | Target |
|---|------|--------|
| 2-1 | `supersede_knowledge()` メソッド実装（フロントマター更新） | `core/memory/manager.py` |
| 2-2 | merge実行ロジック（LLM統合 + 元ファイルアーカイブ + 新ファイル作成） | `core/memory/consolidation.py` |
| 2-3 | coexist実行ロジック（条件注釈付きで両方保持） | `core/memory/consolidation.py` |
| 2-4 | `retriever.py` にsuperseded知識フィルタ追加 | `core/memory/rag/retriever.py` |
| 2-5 | `indexer.py` にsupersedes関連メタデータ連携 | `core/memory/rag/indexer.py` |
| 2-6 | Phase 2のユニットテスト（各解決アクション、RAGフィルタ） | `tests/` |

**Completion condition**: supersede/merge/coexistの各アクションが実行され、RAG検索からsuperseded知識が除外される

### Phase 3: パイプライン統合 + 初回スキャン

| # | Task | Target |
|---|------|--------|
| 3-1 | `daily_consolidate()` に矛盾検出・解決ステージを組み込み | `core/memory/consolidation.py` |
| 3-2 | `weekly_integrate()` に初回矛盾スキャンを組み込み（マーカーで1回実行制御） | `core/memory/consolidation.py` |
| 3-3 | 矛盾解決のアクティビティログ記録（`knowledge_contradiction_resolved` イベント） | `core/memory/consolidation.py` |
| 3-4 | Phase 3の統合テスト（日次固定化E2E、週次統合E2E、初回スキャン） | `tests/` |

**Completion condition**: 日次固定化で矛盾検出・解決が自動実行され、週次統合の初回スキャンで既存矛盾が検出・解決される

## Scope

### In Scope

- 矛盾検出（NLI + LLM判定）
- 矛盾解決の3戦略（supersede/merge/coexist）
- supersedes/superseded_by/valid_until フロントマターフィールド管理
- RAG retriever のsuperseded知識フィルタリング
- 既存knowledge間の初回矛盾スキャン（週次統合に組み込み）
- 矛盾解決のアクティビティログ記録

### Out of Scope

- 解決伝播メカニズム（`shared/resolutions.jsonl`）との統合 — 理由: 既存の仕組みは課題解決用であり、知識矛盾とは異なるドメイン。将来的に統合検討
- Priming時のsuperseded知識の注釈表示 — 理由: RAGフィルタで除外されるため現時点では不要
- 矛盾解決の人間レビューUI — 理由: 夜間バッチ自動化優先。将来拡張
- knowledge以外の記憶タイプ（episodes, procedures）の矛盾検出 — 理由: 知識の矛盾が最も影響が大きい。他タイプは別途検討

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| NLI False Positiveで有用な知識がsupersedeされる | 知識の誤無効化 | LLM判定ステージで二重チェック。supersede後もファイルは保持されリカバリ可能 |
| 初回矛盾スキャンで大量の矛盾が検出され処理時間が長大 | 週次統合の所要時間増大 | 1回あたり20ペア上限。複数週で段階的に処理 |
| merge時のLLMが情報を落とす | 知識の情報損失 | merge前のファイルを`archive/merged/`に保存。7日間保持 |
| supersededフィルタがPriming/意図的検索の両方で効く | 無効化された知識に一切アクセスできなくなる | `include_superseded=True` オプションでデバッグ時に全件検索可能 |

## Acceptance Criteria

- [ ] 新規知識と矛盾する既存知識がNLIで検出される
- [ ] 検出された矛盾がLLMでsupersede/merge/coexistのいずれかに解決される
- [ ] supersede時に旧知識のフロントマターに`superseded_by` + `valid_until`が設定される
- [ ] supersede時に新知識のフロントマターに`supersedes`が設定される
- [ ] merge時に元の2件がarchive/merged/に保存される
- [ ] RAG検索でsuperseded知識（`valid_until`設定済み）がデフォルト除外される
- [ ] `include_superseded=True` で全件検索が可能
- [ ] 初回週次統合で既存knowledge間の矛盾スキャンが実行される
- [ ] 矛盾解決のアクティビティログに`knowledge_contradiction_resolved`イベントが記録される
- [ ] テストカバレッジ80%以上

## References

- `core/memory/consolidation.py:53-143` — `daily_consolidate()` 日次固定化メインフロー
- `core/memory/consolidation.py:283-285` — 既存knowledgeファイル名のみ渡し（矛盾の根本原因）
- `core/memory/consolidation.py:411-412` — append方式の書き込み
- `core/memory/consolidation.py:500-584` — `weekly_integrate()` 週次統合メインフロー
- `core/memory/consolidation.py:656-762` — `_merge_knowledge_files()` 統合プロンプト（L693: 「矛盾はより新しい方を採用」）
- `core/memory/rag/retriever.py` — RAG検索（フィルタリング追加対象）
- `core/memory/rag/indexer.py:377-419` — `_extract_metadata()` メタデータ付与
- `core/memory/manager.py:789-800` — `write_knowledge()` 現行書き込み
- `docs/memory.md` — 記憶システム設計仕様書
- `20260218_consolidation-validation-pipeline.md` — 前提Issue（フロントマター基盤）
- [AGM Belief Revision](https://plato.stanford.edu/entries/logic-belief-revision/) — 信念修正理論（最小変更原則の理論的基盤）
- [Zep Temporal KG](https://www.emergentmind.com/topics/zep-a-temporal-knowledge-graph-architecture) — 時間的知識管理のアーキテクチャ参考
- [mDeBERTa-v3-base-xnli](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7) — 多言語NLIモデル（Issue 1と共有）
- [Contradiction Detection in RAG](https://arxiv.org/html/2504.00180v1) — RAGにおける矛盾検出の課題
- [CRDL: Detect-Then-Resolve](https://www.mdpi.com/2227-7390/12/15/2318) — LLM活用矛盾解決フレームワーク
