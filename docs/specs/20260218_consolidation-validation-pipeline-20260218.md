# 記憶固定化バリデーションパイプライン — NLI+LLMカスケード検証による固定化品質保証

## Overview

日次固定化（episodes/ → knowledge/）のLLM出力にハルシネーションが混入するリスクに対し、NLI+LLMカスケード検証パイプラインを導入する。合わせて、knowledgeファイルにフレームワーク管理のYAMLフロントマターを導入し、既存の品質問題（既存knowledge内容未参照、元ファイル即時削除、コードフェンス残存）を修正する。

## Problem / Background

### Current State

- 日次固定化でLLMが抽出した知識の品質検証が**一切行われていない** — `core/memory/consolidation.py:364-469`
- LLMプロンプトに既存knowledgeファイルの**名前のみ**渡しており、内容は渡していない — `core/memory/consolidation.py:283-285`。LLMは既存知識との重複・矛盾を判断できない
- LLMレスポンスのフォーマット検証・リトライがない。パース失敗時はサイレントに空結果 — `core/memory/consolidation.py:461-467`
- 週次統合で元ファイルを即座に削除しており、ロールバック不可 — `core/memory/consolidation.py:746-747`
- 生成されたknowledgeファイルにMarkdownコードフェンス（` ```markdown `）が残存 — 実ファイル確認済み
- knowledgeファイルにYAMLフロントマターがなく、メタデータ（作成日時、ソースエピソード、信頼度）がファイル上に構造化されていない

### Root Cause

1. **品質検証の不在**: 固定化パイプラインに「生成→書き込み」しかなく、「生成→検証→書き込み」のステップが設計されていない — `core/memory/consolidation.py:104-112`
2. **既存knowledge未参照**: `_summarize_episodes()` のプロンプトがファイル名一覧のみ渡しており、LLMが既存内容を見ずに新規知識を生成する — `core/memory/consolidation.py:283-285`
3. **サニタイズ不足**: `_merge_to_knowledge()` がLLMの出力をそのまま書き込む。コードフェンスや不正フォーマットの除去がない — `core/memory/consolidation.py:411-412`
4. **メタデータの非構造化**: `[AUTO-CONSOLIDATED: ...]` のテキストマーカーのみで、パース可能な構造化メタデータがない

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/memory/consolidation.py` | Direct | 固定化の品質改善。バリデーション・サニタイズ追加 |
| `core/memory/manager.py` | Direct | knowledge読み書きのフロントマター対応 |
| `core/memory/rag/indexer.py` | Direct | チャンキング時のフロントマター除去 |
| `core/memory/rag/retriever.py` | Indirect | confidence メタデータによる検索重み付け（将来拡張） |
| `core/memory/priming.py` | Indirect | Primingで注入されるknowledgeの品質向上 |
| `core/memory/forgetting.py` | Indirect | confidence による忘却優先度判定（将来拡張） |

## Decided Approach / 確定方針

### Design Decision

確定: **NLI + LLMカスケード検証**。ローカルNLIモデル（`MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`）で元エピソードとの整合性を高速判定し、neutral/低信頼のケースのみLLMセルフレビューに回す。夜間バッチ実行のためリアルタイム性は不要であり、品質最優先でコスト増を許容する。合わせて、knowledgeファイルにフレームワーク管理のYAMLフロントマターを導入し、信頼度スコア等のメタデータを構造化管理する。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| A: NLIベース検証のみ | 最安コスト、ローカル完結 | 日本語NLIのニュアンス判定に限界。neutral判定が多発し実質的品質改善不足 | **Rejected**: NLI単体では検出漏れ（recall不足）のリスクが高い |
| B: LLMセルフレビューのみ | NLIモデル追加不要。実装シンプル | Anima数増加時にLLMコストがリニア増大。全件LLM呼出し必須 | **Rejected**: スケーラビリティ不足。10+ Anima運用時にコストが問題化する |
| **C: NLI + LLMカスケード (Adopted)** | NLIで80%+を高速処理。残りのみLLMコスト | NLIモデルの追加導入が必要 | **Adopted**: コスト効率とスケーラビリティのバランスが最良 |
| ChromaDBメタデータのみ管理 | ファイル変更不要 | DB障害時リカバリ困難。デバッグが不便 | **Rejected**: ファイルベースのメタデータの方が可観測性・耐障害性が高い |

### Key Decisions from Discussion

1. **NLIモデル選定: `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`** — 日本語対応の多言語NLIモデル。ローカルGPU推論可能。sentence-transformersと同じHugging Faceエコシステム
2. **メタデータ形式: YAMLフロントマター** — フレームワークが完全管理。LLMは本文のみ生成・参照。`[AUTO-CONSOLIDATED: ...]` テキストマーカーを構造化メタデータに移行
3. **既存knowledgeコンテキスト**: 日次固定化プロンプトにファイル名だけでなく、RAGで関連する既存knowledge本文（上位3件、合計2000トークン上限）も渡す
4. **週次統合のアーカイブ方式**: 元ファイル即時削除 → `archive/merged/` に移動。7日間保持後に削除
5. **信頼度スコア体系**: NLI=entailment→0.9、LLMレビュー合格→0.7、未検証レガシー→0.5
6. **レガシーファイルマイグレーション**: 日次固定化の冒頭でマイグレーション済みかチェックし、初回のみ自動実行

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/memory/consolidation.py` | Modify | バリデーションステージ追加、既存knowledgeコンテキスト渡し改善、フォーマットサニタイズ、リトライロジック、アーカイブ方式変更、マイグレーション |
| `core/memory/manager.py` | Modify | knowledge読み書きのフロントマター対応（付与・パース・ストリップ） |
| `core/memory/rag/indexer.py` | Modify | チャンキング時のフロントマター除去、confidenceメタデータ連携 |
| `core/memory/validation.py` | New | NLIモデルロード・推論、グラウンディング検証、LLMレビューのロジック |
| `core/memory/forgetting.py` | No change | 将来的にconfidenceベースの忘却優先度導入可能だが今回はスコープ外 |

#### Change 1: バリデーションステージ追加

**Target**: `core/memory/consolidation.py` — `daily_consolidate()`

```python
# Before (L104-112)
summaries = await self._summarize_episodes(episodes_text, knowledge_list, resolved_events)
affected = await self._merge_to_knowledge(summaries)
await self._update_rag_index(affected)

# After
summaries = await self._summarize_episodes(episodes_text, knowledge_list, knowledge_context, resolved_events)
sanitized = self._sanitize_llm_output(summaries)           # コードフェンス除去
validated = await self._validate_knowledge(sanitized, episodes_text)  # NLI+LLMカスケード
affected = await self._merge_to_knowledge(validated)        # confidence付きで書き込み
await self._update_rag_index(affected)
```

#### Change 2: 既存knowledgeコンテキスト追加

**Target**: `core/memory/consolidation.py` — `_summarize_episodes()`

```python
# Before (L283-285): ファイル名一覧のみ
knowledge_list = "\n".join(f"- {name}" for name in knowledge_names)

# After: RAGで関連knowledge本文も取得
related_knowledge = await self._fetch_related_knowledge(episodes_text, top_k=3, max_tokens=2000)
knowledge_context = "\n\n".join(
    f"### {name}\n{content}" for name, content in related_knowledge
)
# プロンプトに追加:
# 【関連する既存知識の内容】
# {knowledge_context}
```

#### Change 3: YAMLフロントマターの読み書き

**Target**: `core/memory/manager.py`

```python
# 書き込み
def write_knowledge_with_meta(self, path: Path, content: str, metadata: dict) -> None:
    frontmatter = yaml.dump(metadata, default_flow_style=False, allow_unicode=True)
    path.write_text(f"---\n{frontmatter}---\n\n{content}", encoding="utf-8")

# 読み出し（LLM向け: フロントマター除去）
def read_knowledge_content(self, path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text

# メタデータ読み出し
def read_knowledge_metadata(self, path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return yaml.safe_load(parts[1]) or {}
    return {}
```

#### Change 4: validation.py 新規モジュール

**Target**: `core/memory/validation.py` (New)

```python
class KnowledgeValidator:
    """NLI + LLMカスケードによる固定化品質検証"""

    NLI_MODEL = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
    CONTRADICTION_THRESHOLD = 0.7   # NLI contradictionラベルの確信度閾値
    ENTAILMENT_THRESHOLD = 0.6      # NLI entailmentラベルの確信度閾値

    async def validate(self, knowledge_items: list[dict], source_episodes: str) -> list[dict]:
        """
        各knowledge itemをソースエピソードに対して検証する。
        Returns: confidence付きのknowledge items。contradiction判定のものは除外。
        """
        results = []
        for item in knowledge_items:
            nli_result = self._nli_check(item["content"], source_episodes)
            if nli_result.label == "entailment" and nli_result.score >= self.ENTAILMENT_THRESHOLD:
                item["confidence"] = 0.9
                results.append(item)
            elif nli_result.label == "contradiction" and nli_result.score >= self.CONTRADICTION_THRESHOLD:
                logger.warning("Knowledge rejected (NLI contradiction): %s", item["content"][:100])
                # 除外 — knowledgeに書き込まない
            else:
                # neutral or 低確信度 → LLMレビュー
                llm_ok = await self._llm_review(item["content"], source_episodes)
                if llm_ok:
                    item["confidence"] = 0.7
                    results.append(item)
                else:
                    logger.warning("Knowledge rejected (LLM review): %s", item["content"][:100])
        return results
```

### Edge Cases

| Case | Handling |
|------|----------|
| NLIモデルがGPUメモリに載らない | `device="cpu"` にフォールバック。夜間バッチなので速度低下許容 |
| NLIモデルのダウンロード/ロード失敗 | NLIステップをスキップし全件LLMレビュー（B案相当フォールバック） |
| LLMレスポンスがフォーマット違反 | 「JSON形式で出力してください」の修正プロンプトで1回リトライ。それでも失敗なら当該バッチスキップ+warningログ |
| エピソードが0件の日 | 固定化自体をスキップ（現行動作維持） |
| 既存knowledgeが50+ファイルの場合 | RAGコンテキストは上位3件・合計2000トークン上限に制限 |
| レガシーファイルのマイグレーション | `{anima_dir}/knowledge/.migrated` マーカーで1回実行制御。バックアップ → パース → フロントマター付与 → クリーニング |
| マイグレーション中のクラッシュ | バックアップから復元可能。マーカー未作成のため次回再実行 |
| フロントマター未付与ファイルの読み出し | `read_knowledge_content()` がフロントマターの有無を判定し、両形式に対応 |

## Implementation Plan

### Phase 1: YAMLフロントマター基盤 + マイグレーション

| # | Task | Target |
|---|------|--------|
| 1-1 | `manager.py` にフロントマター読み書きメソッド追加（`write_knowledge_with_meta`, `read_knowledge_content`, `read_knowledge_metadata`） | `core/memory/manager.py` |
| 1-2 | `_chunk_by_markdown_headings()` にフロントマターストリップ処理追加 | `core/memory/rag/indexer.py` |
| 1-3 | `_migrate_legacy_knowledge()` メソッド実装（バックアップ → パース → フロントマター付与 → クリーニング） | `core/memory/consolidation.py` |
| 1-4 | Phase 1のユニットテスト（フロントマター読み書き、マイグレーション、後方互換性） | `tests/` |

**Completion condition**: フロントマター付きknowledgeファイルの読み書きが動作し、レガシーファイルが自動マイグレーションされる

### Phase 2: バリデーションモジュール

| # | Task | Target |
|---|------|--------|
| 2-1 | `KnowledgeValidator` クラス実装（NLIモデルロード・推論） | `core/memory/validation.py` |
| 2-2 | NLIフォールバック（GPU→CPU、モデルロード失敗→LLMのみ）の実装 | `core/memory/validation.py` |
| 2-3 | LLMセルフレビューメソッド実装（元エピソードとの照合プロンプト） | `core/memory/validation.py` |
| 2-4 | Phase 2のユニットテスト（NLI判定、LLMレビュー、フォールバック） | `tests/` |

**Completion condition**: NLI+LLMカスケード検証が単体で動作し、entailment/contradiction/neutralの各パスが正しく処理される

### Phase 3: 固定化パイプライン統合 + 既存問題修正

| # | Task | Target |
|---|------|--------|
| 3-1 | `daily_consolidate()` にバリデーションステージを組み込み | `core/memory/consolidation.py` |
| 3-2 | `_summarize_episodes()` に既存knowledgeコンテキスト（RAG上位3件）を追加 | `core/memory/consolidation.py` |
| 3-3 | `_sanitize_llm_output()` メソッド追加（コードフェンス除去） | `core/memory/consolidation.py` |
| 3-4 | `_merge_to_knowledge()` でフロントマター付き書き込みに変更 | `core/memory/consolidation.py` |
| 3-5 | フォーマット検証リトライ（パース失敗時に1回リトライ）追加 | `core/memory/consolidation.py` |
| 3-6 | 週次統合の元ファイルを `archive/merged/` に移動する方式に変更 | `core/memory/consolidation.py` |
| 3-7 | Phase 3の統合テスト（日次固定化E2E、週次統合E2E） | `tests/` |

**Completion condition**: 日次固定化でNLI+LLMカスケード検証が実行され、検証済みknowledgeファイルにconfidence付きフロントマターが書き込まれる

## Scope

### In Scope

- NLI + LLMカスケード検証パイプライン（`validation.py` 新設）
- YAMLフロントマター基盤（`manager.py` 変更）
- 既存knowledgeファイルのマイグレーション（フロントマター付与 + クリーニング）
- 既存knowledgeコンテキストの日次固定化プロンプト注入
- コードフェンスサニタイズ
- フォーマット検証リトライ
- 週次統合の元ファイルアーカイブ化
- 信頼度スコア（confidence）の付与

### Out of Scope

- 矛盾検出・解決メカニズム — 理由: 別Issue（`20260218_knowledge-contradiction-detection-resolution.md`）で対応。本Issueのフロントマター基盤が前提
- Self-Consistency（複数サンプリング）の追加 — 理由: 将来拡張。現時点ではNLI+LLM1回で十分な品質
- `max_tokens` のバッチ分割対応 — 理由: 現状のエピソード量では2048トークンで概ね収まっている
- Priming/Forgettingへのconfidence連携 — 理由: 将来拡張。本Issueではメタデータ付与まで

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| NLIモデルが日本語テキストで誤判定（False Positive/Negative）する | 有用な知識がrejectされる、またはハルシネーションが通過する | NLI閾値をチューニング可能に設計。フォールバックでLLMレビューが捕捉する |
| NLIモデルのメモリ使用量がGPUに収まらない | 推論速度低下 | CPU推論フォールバック。夜間バッチなので許容 |
| マイグレーションでファイル破損 | knowledge損失 | `archive/pre_migration/` にバックアップ後にマイグレーション |
| LLMレビューのコスト増 | 月間API費用増加 | NLIで80%+をフィルタし、LLM呼出しは残り20%以下に抑える |

## Acceptance Criteria

- [ ] 日次固定化で生成されたknowledgeが元エピソードに対してNLI検証されている
- [ ] NLI=contradiction（確信度0.7以上）の知識がknowledgeに書き込まれない
- [ ] NLI=neutral/低確信度の知識がLLMレビューを経てから書き込まれる
- [ ] knowledgeファイルにYAMLフロントマター（created_at, source_episodes, confidence, auto_consolidated）が付与されている
- [ ] 既存knowledgeファイルが初回実行時に自動マイグレーションされる（バックアップ付き）
- [ ] マイグレーション後のファイルからMarkdownコードフェンスが除去されている
- [ ] 日次固定化プロンプトに関連する既存knowledge本文が含まれている
- [ ] 週次統合の元ファイルがarchive/merged/に移動される（即時削除されない）
- [ ] NLIモデル未利用時にLLMフォールバックが動作する
- [ ] フロントマター未付与ファイルの読み出しが後方互換で動作する
- [ ] テストカバレッジ80%以上

## References

- `core/memory/consolidation.py:53-143` — `daily_consolidate()` 日次固定化メインフロー
- `core/memory/consolidation.py:258-362` — `_summarize_episodes()` LLM呼出しプロンプト
- `core/memory/consolidation.py:364-469` — `_merge_to_knowledge()` レスポンスパース・書き込み
- `core/memory/consolidation.py:500-584` — `weekly_integrate()` 週次統合メインフロー
- `core/memory/consolidation.py:656-762` — `_merge_knowledge_files()` 週次統合LLM呼出し
- `core/memory/consolidation.py:746-747` — 元ファイル即時削除箇所
- `core/memory/manager.py:789-800` — `write_knowledge()` 現行の書き込み
- `core/memory/rag/indexer.py:255-309` — `_chunk_by_markdown_headings()` チャンキング
- `core/memory/rag/indexer.py:377-419` — `_extract_metadata()` メタデータ付与
- `docs/memory.md` — 記憶システム設計仕様書
- [MiniCheck](https://arxiv.org/abs/2404.10774) — 低コストファクトチェックモデル
- [SelfCheckGPT](https://arxiv.org/abs/2303.08896) — ゼロリソースハルシネーション検出
- [HaluGate](https://blog.vllm.ai/2025/12/14/halugate.html) — 2段階バリデーションパイプライン
- [mDeBERTa-v3-base-xnli](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7) — 多言語NLIモデル
- `20260218_knowledge-contradiction-detection-resolution.md` — 本Issueのフロントマター基盤を前提とする後続Issue
