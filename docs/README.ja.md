# AnimaWorks ドキュメント

**[English](README.md)**

一人では何もできない。だから、組織を作った。

天才一人より、不完全な個が協働するチームのほうが強い。精神科医としてLLMを診たとき、人間の脳と驚くほど似た構造に気づいた。ならば、LLMにも脳と同じ記憶を与え、組織として動かせるはずだ。経験を積み重ね、教訓を抽出し、使わない記憶は忘れていく——そうやって成長する「人」の集まりを、コードで定義する。それがAnimaWorksだ。

このページは、その全体像を理解するための入口である。

---

## どこから読むか

### はじめて触る方

1. **[機能一覧](features.ja.md)** — AnimaWorksで何ができるかの全体像
2. **[CLIリファレンス](cli-reference.ja.md)** — セットアップから日常運用までのコマンド一覧
3. **[APIリファレンス](api-reference.ja.md)** — REST APIの仕様（Web UIやスクリプト連携に）
4. **[Slack連携ガイド](slack-socket-mode-setup.ja.md)** — SlackからAnimaと会話するための設定手順

### 設計思想やアーキテクチャに関心がある方

1. **[設計理念](vision.ja.md)** — 「不完全な個の協働」という根本思想
2. **[技術仕様](spec.ja.md)** — アーキテクチャ、実行モード、設定体系の全容
3. **[記憶システム](memory.ja.md)** — エピソード記憶・意味記憶・手続き記憶・プライミング・忘却
4. **[セキュリティ](security.ja.md)** — 多層防御モデルと敵対的脅威分析

### 脳科学・研究に関心がある方

1. **[コンテキストウィンドウの幻想](paper/context-window-illusion.ja.md)** — コンテキスト拡大では解決しない認知限界と、生体模倣型メモリの設計根拠
2. **[脳科学マッピング](brain-mapping.ja.md)** — AnimaWorksの各モジュールと人間の脳の対応関係
3. **[記憶システム](memory.ja.md)** — 海馬・新皮質・基底核の機能を再現する記憶アーキテクチャ
4. **[設計理念](vision.ja.md)** — 精神科医がなぜこのフレームワークを作ったか

---

## ドキュメント一覧

### 基本コンセプト

| ドキュメント | 概要 |
|-------------|------|
| [設計理念](vision.ja.md) | 「不完全な個の協働が、単一の全能者より堅牢な組織を作る」。カプセル化・書庫型記憶・自律性の3原則と、適材適所のマルチモデル設計 |
| [機能一覧](features.ja.md) | 自律エージェント、記憶ライフサイクル、組織構造、マルチモデル対応、音声チャットなど全機能の概説 |

### リファレンス

| ドキュメント | 概要 |
|-------------|------|
| [CLIリファレンス](cli-reference.ja.md) | `animaworks` コマンドの全サブコマンド・オプション。初期化、サーバー管理、Anima操作、チャット、モデル管理、RAG修復、メモリバックエンド、Skill Hub、TaskBoard |
| [APIリファレンス](api-reference.ja.md) | REST APIの全エンドポイント。認証、Anima管理、チャット（SSEストリーミング）、記憶操作、設定、Webhook |
| [Slack連携ガイド](slack-socket-mode-setup.ja.md) | Slack Socket Modeの設定手順。Slack Appの作成からAnimaとの接続まで。パブリックURL不要で動作する |

### アーキテクチャ詳説

| ドキュメント | 概要 |
|-------------|------|
| [技術仕様](spec.ja.md) | 要件定義書。6つの実行モード（S/C/D/G/A/B）、プロンプト構築、実行パス分離、設定解決の優先度 |
| [記憶システム](memory.ja.md) | 人間の記憶モデルとの対応、RAG検索、自動想起、action memory gate、日次/週次の記憶統合、能動的忘却 |
| [セキュリティ](security.ja.md) | 脅威モデル、データ出自追跡（Provenance）、信頼レベル分類、コマンド実行制御、パストラバーサル防御、認証 |
| [脳科学マッピング](brain-mapping.ja.md) | LLMを大脳新皮質、プライミングを海馬、忘却を睡眠依存メカニズムに対応させた設計の詳細。精神科医としての臨床知見に基づく |

### 研究

| ドキュメント | 概要 |
|-------------|------|
| [コンテキストウィンドウの幻想](paper/context-window-illusion.ja.md) | コンテキスト拡大の歴史、利用率10〜30%を超えると劣化する実証、精神医学的な認知障害との構造的類似、そして生体模倣型メモリアーキテクチャの提案 |

### リリースノート

| バージョン | 概要 |
|-----------|------|
| [v0.5](release/v0.5.ja.md) | RAG全面移行、セキュリティ多層化（Provenance 4フェーズ）、Workspace UI全面刷新、ストリーミング高速化 |

---

## 設計仕様（specs/）

個別の機能設計・実装仕様。開発に参加する場合や、内部の設計判断を理解したい場合に参照する。

### 記憶システム

| 日付 | 仕様 |
|------|------|
| 2026-02-14 | [Primingレイヤー設計](specs/20260214_priming-layer_design.md) |
| 2026-02-18 | [Primingフォーマット再設計](specs/20260218_priming-format-redesign_implemented-20260218.md) |
| 2026-02-18 | [統一アクティビティログ](specs/20260218_unified-activity-log-implemented-20260218.md) |
| 2026-02-18 | [アクティビティログ仕様準拠修正](specs/20260218_activity-log-spec-compliance-fixes-implemented-20260218.md) |
| 2026-02-18 | [ストリーミングジャーナル（WAL）](specs/20260218_streaming-journal-implemented-20260218.md) |
| 2026-02-18 | [エピソード重複排除・状態自動更新・解決伝播](specs/20260218_episode-dedup-state-autoupdate-resolution-propagation.md) |
| 2026-02-18 | [記憶統合バリデーションパイプライン](specs/20260218_consolidation-validation-pipeline-20260218.md) |
| 2026-02-18 | [知識矛盾検出・解決](specs/20260218_knowledge-contradiction-detection-resolution-20260218.md) |
| 2026-02-18 | [記憶システム強化チェックリスト](specs/20260218_memory-system-enhancement-checklist-20260218.md) |

### 手続き記憶

| 日付 | 仕様 |
|------|------|
| 2026-02-18 | [手続き記憶の基盤](specs/20260218_procedural-memory-foundation-20260218.md) |
| 2026-02-18 | [手続き記憶の自動蒸留](specs/20260218_procedural-memory-auto-distillation-20260218.md) |
| 2026-02-18 | [手続き記憶の再統合](specs/20260218_procedural-memory-reconsolidation-20260218.md) |
| 2026-02-18 | [手続き記憶のユーティリティと忘却](specs/20260218_procedural-memory-utility-forgetting-20260218.md) |

### セキュリティ

| 日付 | 仕様 |
|------|------|
| 2026-02-15 | [記憶書き込みセキュリティ](specs/20260215_memory-write-security-20260216.md) |
| 2026-02-28 | [コマンドインジェクション対策](specs/20260228_security-command-injection-fix.md) |
| 2026-02-28 | [パストラバーサル対策](specs/20260228_security-path-traversal-fix.md) |

### データ出自追跡（Provenance）

| 日付 | 仕様 |
|------|------|
| 2026-02-28 | [Phase 1: 基盤](specs/20260228_provenance-1-foundation.md) |
| 2026-02-28 | [Phase 2: 入力境界](specs/20260228_provenance-2-input-boundary.md) |
| 2026-02-28 | [Phase 3: 伝播](specs/20260228_provenance-3-propagation.md) |
| 2026-02-28 | [Phase 4: RAG出自](specs/20260228_provenance-4-rag-provenance.md) |
| 2026-02-28 | [Phase 5: Mode S信頼](specs/20260228_provenance-5-mode-s-trust.md) |

### ツール

| 日付 | 仕様 |
|------|------|
| 2026-03-07 | [汎用Notionツール](specs/20260307_generic-notion-tool_implemented-20260307.md) |
