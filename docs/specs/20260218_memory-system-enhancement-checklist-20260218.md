# 記憶システム強化 統合チェックリスト — 固定化品質保証・矛盾解決・手続き記憶ライフサイクル

## Overview

memory.md レビューで特定された6つの改善Issueの統合実装チェックリスト。依存関係に基づく実装順序を定義し、各Issueのフェーズ単位で進捗を追跡する。

## 背景

記憶システム設計仕様書（`docs/memory.md`）のレビューで以下の課題が特定された:

1. **LLM固定化の品質保証の欠如** — ハルシネーションが knowledge/ に永続化するリスク
2. **矛盾する記憶の解決メカニズムの不在** — 古い知識と新しい知識の矛盾が放置される
3. **手続き記憶のライフサイクル管理の不在** — procedures/ に自動化された作成・更新・忘却がない

これらを6つのIssueに分解し、依存関係を考慮した実装順序で解決する。

## 依存関係

```
Wave 1（並列可能）
├── Issue 1: 固定化バリデーション
└── Issue 3: 手続き記憶基盤整備

Wave 2（Wave 1完了後、内部は並列可能）
├── Issue 2: 矛盾検出・解決        ← Issue 1
├── Issue 4: 自動蒸留              ← Issue 3
└── Issue 5: 再固定化              ← Issue 3

Wave 3
└── Issue 6: 効用ベース忘却        ← Issue 3 + Issue 5
```

## 共有リソース

以下のコンポーネントは複数Issueで変更される。実装順序を守ることでコンフリクトを回避する。

| ファイル | 変更するIssue | 注意点 |
|---------|--------------|--------|
| `core/memory/consolidation.py` | 1, 2, 4, 5 | 日次固定化フローへのステージ追加順序を厳守 |
| `core/memory/manager.py` | 1, 3, 5 | frontmatter読み書きはIssue 1で基盤構築、Issue 3で拡張 |
| `core/memory/forgetting.py` | 6 | Issue 6のみ。他Issueとの競合なし |
| `core/memory/validation.py` | 1, 2 | Issue 1で新設、Issue 2で拡張 |
| `core/memory/rag/indexer.py` | 1, 2, 3 | frontmatterストリップ + メタデータ連携 |
| `core/memory/rag/retriever.py` | 2 | supersededフィルタ追加 |
| `core/prompt/builder.py` | 3 | procedures注入追加 |
| `core/tooling/handler.py` | 3 | RAGインデックス更新 + report_procedure_outcome |
| NLIモデル（mDeBERTa） | 1, 2 | Issue 1でロード基盤構築、Issue 2で共有 |

---

## Wave 1: 基盤構築（並列実装可能）

### Issue 1: 記憶固定化バリデーションパイプライン

> `docs/issues/20260218_consolidation-validation-pipeline.md`

- [ ] **Phase 1: YAMLフロントマター基盤 + マイグレーション**
  - [ ] 1-1: manager.py にフロントマター読み書きメソッド追加
  - [ ] 1-2: indexer.py にフロントマターストリップ処理追加
  - [ ] 1-3: レガシーknowledgeファイルの自動マイグレーション実装
  - [ ] 1-4: ユニットテスト（フロントマター読み書き、マイグレーション、後方互換性）
- [ ] **Phase 2: バリデーションモジュール**
  - [ ] 2-1: KnowledgeValidator クラス実装（NLIモデルロード・推論）
  - [ ] 2-2: NLIフォールバック（GPU→CPU、ロード失敗→LLMのみ）
  - [ ] 2-3: LLMセルフレビューメソッド実装
  - [ ] 2-4: ユニットテスト（NLI判定、LLMレビュー、フォールバック）
- [ ] **Phase 3: パイプライン統合 + 既存問題修正**
  - [ ] 3-1: daily_consolidate() にバリデーションステージ組み込み
  - [ ] 3-2: 既存knowledgeコンテキスト（RAG上位3件）の追加
  - [ ] 3-3: コードフェンスサニタイズ
  - [ ] 3-4: フロントマター付き書き込み
  - [ ] 3-5: フォーマット検証リトライ
  - [ ] 3-6: 週次統合のアーカイブ方式変更（即時削除→archive/merged/）
  - [ ] 3-7: 統合テスト（日次固定化E2E、週次統合E2E）

### Issue 3: 手続き記憶基盤整備

> `docs/issues/20260218_procedural-memory-foundation.md`

- [ ] **Phase 1: frontmatter基盤**
  - [ ] 1-1: procedures用frontmatter読み書きメソッド追加
  - [ ] 1-2: procedures用ソフトバリデーション追加
  - [ ] 1-3: indexer.py のfrontmatterストリップ処理追加
  - [ ] 1-4: 既存proceduresのマイグレーション実装
  - [ ] 1-5: ユニットテスト
- [ ] **Phase 2: 3-tierマッチング + 自動注入**
  - [ ] 2-1: match_skills_by_description() をprocedures対応に拡張
  - [ ] 2-2: builder.py でprocedures/ マッチング追加 + 注入追跡記録
  - [ ] 2-3: Priming Channel D にprocedures/ 追加
  - [ ] 2-4: ユニットテスト
- [ ] **Phase 3: RAGインデックス更新 + 成功/失敗追跡**
  - [ ] 3-1: write_memory_file 後のRAGインデックス自動更新
  - [ ] 3-2: report_procedure_outcome ツール実装
  - [ ] 3-3: フレームワーク自動成否追跡（注入記録→セッション境界判定）
  - [ ] 3-4: 統合テスト

**Wave 1 完了条件**: Issue 1, 3 の全フェーズが完了し、テストが通ること

---

## Wave 2: 検出・蒸留・更新（Wave 1完了後、内部は並列可能）

### Issue 2: 知識矛盾検出・解決メカニズム

> `docs/issues/20260218_knowledge-contradiction-detection-resolution.md`
> 前提: Issue 1 完了

- [ ] **Phase 1: 矛盾検出ロジック**
  - [ ] 1-1: ContradictionDetector クラス実装（NLIペア判定）
  - [ ] 1-2: LLM矛盾解決プロンプト（supersede/merge/coexist判定）
  - [ ] 1-3: ユニットテスト
- [ ] **Phase 2: 解決実行ロジック**
  - [ ] 2-1: supersede_knowledge() メソッド実装
  - [ ] 2-2: merge実行ロジック
  - [ ] 2-3: coexist実行ロジック
  - [ ] 2-4: retriever.py にsupersedフィルタ追加
  - [ ] 2-5: indexer.py にsupersedes関連メタデータ連携
  - [ ] 2-6: ユニットテスト
- [ ] **Phase 3: パイプライン統合 + 初回スキャン**
  - [ ] 3-1: daily_consolidate() に矛盾検出・解決ステージ組み込み
  - [ ] 3-2: weekly_integrate() に初回矛盾スキャン組み込み
  - [ ] 3-3: activity_log への矛盾解決イベント記録
  - [ ] 3-4: 統合テスト

### Issue 4: エピソード→手続きの自動蒸留

> `docs/issues/20260218_procedural-memory-auto-distillation.md`
> 前提: Issue 3 完了

- [ ] **Phase 1: 日次固定化の振り分け**
  - [ ] 1-1: _summarize_episodes() プロンプト拡張（knowledge/procedures振り分け）
  - [ ] 1-2: _merge_to_procedures() メソッド実装
  - [ ] 1-3: 重複チェック（RAG類似度検索）実装
  - [ ] 1-4: ユニットテスト
- [ ] **Phase 2: 週次パターン検出・蒸留**
  - [ ] 2-1: activity_log からのタスクパターンクラスタリング
  - [ ] 2-2: LLMによる共通手順蒸留プロンプト
  - [ ] 2-3: weekly_integrate() へのパターン検出ステージ組み込み
  - [ ] 2-4: 統合テスト

### Issue 5: 予測誤差ベースの手続き再固定化

> `docs/issues/20260218_procedural-memory-reconsolidation.md`
> 前提: Issue 3 完了

- [ ] **Phase 1: 再固定化トリガー + LLM Reflection**
  - [ ] 1-1: _reconsolidate_procedures() メソッド実装
  - [ ] 1-2: LLM Reflectionプロンプト + レスポンスパーサー
  - [ ] 1-3: ユニットテスト
- [ ] **Phase 2: バージョン管理 + パイプライン統合**
  - [ ] 2-1: archive_procedure_version(), update_procedure_version() 実装
  - [ ] 2-2: daily_consolidate() への再固定化ステージ組み込み
  - [ ] 2-3: activity_log への再固定化イベント記録
  - [ ] 2-4: 統合テスト

**Wave 2 完了条件**: Issue 2, 4, 5 の全フェーズが完了し、テストが通ること

---

## Wave 3: ライフサイクル完成

### Issue 6: 効用ベースの手続き記憶忘却

> `docs/issues/20260218_procedural-memory-utility-forgetting.md`
> 前提: Issue 3 + Issue 5 完了

- [ ] **Phase 1: PROTECTED解除 + 閾値設定**
  - [ ] 1-1: PROTECTED_MEMORY_TYPES から procedures 除外
  - [ ] 1-2: _is_protected_procedure() 実装
  - [ ] 1-3: _should_downscale_procedure() 実装
  - [ ] 1-4: ユニットテスト
- [ ] **Phase 2: 統合 + クリーンアップ**
  - [ ] 2-1: Stage 1-3 にprocedures専用パス追加
  - [ ] 2-2: archive/procedure_versions/ のクリーンアップ
  - [ ] 2-3: 統合テスト（日次→週次→月次の全ステージ）

**Wave 3 完了条件**: Issue 6 の全フェーズが完了し、テストが通ること

---

## 最終検証

全Wave完了後の統合検証:

- [ ] 日次固定化のフルパイプラインE2Eテスト（バリデーション→矛盾検出→procedures振り分け→再固定化）
- [ ] 週次統合のフルパイプラインE2Eテスト（重複検出→マージ→パターン蒸留→初回矛盾スキャン）
- [ ] 月次忘却のフルパイプラインE2Eテスト（knowledge忘却→procedures効用ベース忘却→archiveクリーンアップ）
- [ ] docs/memory.md の更新（新機能の反映）
- [ ] 実Anima環境での動作確認（最低1サイクルの日次→週次→月次を通す）

## 日次固定化パイプライン（最終形）

```
daily_consolidate()
│
├── [既存] マイグレーションチェック（Issue 1: フロントマター, Issue 3: procedures）
│
├── [既存] エピソード収集
│
├── [既存] LLM抽出（拡張: knowledge/procedures振り分け — Issue 4）
│
├── [新規] サニタイズ（Issue 1: コードフェンス除去）
│
├── [新規] バリデーション（Issue 1: NLI + LLMカスケード）
│
├── [新規] 矛盾検出・解決（Issue 2: NLI + LLM判定 → supersede/merge/coexist）
│
├── [既存] knowledge/ 書き込み（拡張: フロントマター付き — Issue 1）
│
├── [新規] procedures/ 書き込み（Issue 4: フロントマター付き）
│
├── [既存] RAGインデックス更新
│
├── [新規] 手続き再固定化（Issue 5: 失敗蓄積手順のReflection + 修正）
│
└── [既存] Synaptic Downscaling（拡張: procedures対応 — Issue 6）
```

## Issue一覧

| # | Issue | ファイル | Wave |
|---|-------|---------|------|
| 1 | 固定化バリデーションパイプライン | `20260218_consolidation-validation-pipeline.md` | 1 |
| 2 | 知識矛盾検出・解決メカニズム | `20260218_knowledge-contradiction-detection-resolution.md` | 2 |
| 3 | 手続き記憶基盤整備 | `20260218_procedural-memory-foundation.md` | 1 |
| 4 | エピソード→手続き自動蒸留 | `20260218_procedural-memory-auto-distillation.md` | 2 |
| 5 | 予測誤差ベースの再固定化 | `20260218_procedural-memory-reconsolidation.md` | 2 |
| 6 | 効用ベースの忘却 | `20260218_procedural-memory-utility-forgetting.md` | 3 |
