# CS（カスタマーサクセス）フルチーム — チーム概要

## 2ロール構成

| ロール | 責務 | 推奨 `--role` | `speciality` 例 | 詳細 |
|--------|------|--------------|-----------------|------|
| **CS Lead** | 顧客戦略・オンボーディング計画[machine]・ヘルス分析[machine]・リテンション施策[machine]・VoC集約[machine]・エスカレーション | `manager` | `cs-lead` | `customer-success/cs-lead/` |
| **Support** | チケット対応・FAQ管理・オンボーディング実行・一次対応・VoC素材収集 | `administration` | `cs-support` | `customer-success/support/` |

1つの Anima に全工程を集約すると、顧客分析と一次対応のコンテキスト競合・ヘルス判定の自己検証盲点・VoC集約とチケット対応の優先度衝突が発生する。

各ロールディレクトリに `injection.template.md`（injection.md 雛形）、`machine.md`（machine 活用パターン、CS Lead のみ）、`checklist.md`（品質チェックリスト）がある。

> 基本原則の詳細: `team-design/guide.md`

## 2つの実行モード

### Onboarding mode（計画ベース）

```
営業 Director → cs-handoff.md (draft)
  → CS Lead → Phase A: machine でオンボーディング計画 → CS Lead が検証
    → onboarding-plan.md (approved) → delegate_task → Support
      → Support: オンボーディング実行 → CS Lead に完了報告
```

営業チームから契約成立時に `cs-handoff.md` を受け取り、CS Lead が machine で顧客分析・オンボーディング計画を作成した後、Support に実行を委譲する。

### Maintenance mode（定期巡回ベース）

```
CS Lead → Phase B: Health Tracker 定期分析 (heartbeat/cron)
  → Yellow/Red 検出 → Phase C: machine でリテンション施策ドラフト → CS Lead が検証 → 顧客対応
  → Critical → 上位にエスカレーション
  → 全 Green → 経過観察

CS Lead → Phase D: VoC 集約 (cron: 定期)
  → voc-report.md → COO 経由で開発チームへフィードバック

Support → チケット対応 + FAQ管理 (cron: 日常)
  → 問題発生 → CS Lead に報告
  → CS 問い合わせ以外（営業等）→ 該当チームにエスカレーション
```

## ハンドオフチェーン

```
営業 Director → cs-handoff.md (draft)
  → CS Lead → Phase A: machine で分析・計画 → CS Lead が検証
    → onboarding-plan.md (approved) → delegate_task → Support
      → Support: オンボーディング実行 → CS Lead に完了報告
        → CS Lead: Health Tracker に新規登録 → Maintenance mode へ

CS Lead → Phase B: Health Tracker 分析 (heartbeat/cron)
  → Yellow/Red → Phase C: machine でリテンション施策 → CS Lead が検証 → 実行
  → Phase D: VoC 集約 → voc-report.md → COO

Support → 自律巡回 (cron)
  → チケット対応 → CS Lead に報告
```

### 引き継ぎドキュメント

| 送信元 → 送信先 | ドキュメント | 条件 | 通信手段 |
|----------------|------------|------|---------|
| 営業 Director → CS Lead | `cs-handoff.md` | 契約成立時 | `send_message (intent: report)` |
| CS Lead → Support | `onboarding-plan.md` | `status: approved` | `delegate_task` |
| Support → CS Lead | チケット報告 | 問題発生時 | `send_message (intent: report)` |
| CS Lead → COO | `voc-report.md` | 定期（cron） | `send_message (intent: report)` |
| CS Lead → 上位 | エスカレーション | Critical ヘルススコア | `send_message (intent: report)` |

### 運用ルール

- **修正サイクル**: Critical → 即座に介入 + 上位エスカレーション / Warning → リテンション施策策定 / 3往復解消しない → 人間にエスカレーション
- **Customer Health Score Tracker**: 顧客のヘルススコアを追跡する。silent drop 禁止
- **エスカレーション3層**: Support → CS Lead → 上位（COO等）
- **machine 失敗時**: `current_state.md` に記録 → 次回 heartbeat で再評価

## スケーリング

| 規模 | 構成 | 備考 |
|------|------|------|
| ソロ | CS Lead が全ロール兼務（checklist で品質担保） | 少数顧客、定型対応 |
| ペア | 本テンプレート通り2名 | 標準運用 |
| スケールド | CS Lead + 複数 Support（セグメント別等） | 大規模顧客基盤 |

## 他チームとの対応関係

| 開発チームロール | 法務チームロール | 営業MKTロール | CSロール | 対応する理由 |
|----------------|----------------|-------------|---------|-------------|
| PdM（計画・判断） | Director（分析計画・判断） | Director（戦略・営業執行） | CS Lead（顧客戦略・分析） | 「何をやるか」を決定する司令塔 |
| Engineer（実装） | Director + machine | Director + machine | CS Lead + machine | machine で分析・制作を実行 |
| Reviewer（静的検証） | Verifier（独立検証） | {コンプライアンスレビュアー名}（コンプライアンス） | — | CSでは独立検証ロール不要（対応品質は KPI で担保） |
| Tester（動的検証） | Researcher（根拠検証） | Researcher（市場調査） | Support（一次対応・情報収集） | 顧客接点で情報を収集する |

## KPI 体系（4指標）

| 指標 | 概要 | AI CS での位置づけ |
|------|------|-------------------|
| **CSAT** | 顧客満足度スコア | サーベイベース。対応品質の直接指標 |
| **NPS** | ネットプロモータースコア | 推奨意向。長期的な顧客関係の指標 |
| **チャーン率** | 解約率 | Health Tracker の Yellow/Red で予兆を検出 |
| **オンボーディング完了率** | 新規顧客の初期設定完了率 | cs-handoff.md 受領 → オンボーディング完了の追跡 |

時間系KPI（初回応答時間、解決時間等）はAIエージェントCSでは即時応答（≒0）になるため除外。

## Customer Health Score Tracker — 顧客ヘルススコア追跡表

顧客のヘルススコアを追跡する。Yellow/Red を検出したら Phase C でリテンション施策を策定する。

### 追跡ルール

- 新規顧客はオンボーディング完了後にこの表に登録する
- 次回 Heartbeat / レビュー時に全項目のステータスを更新する
- Yellow/Red の顧客は Phase C でリテンション施策を策定する
- silent drop（言及なしでの消滅）は禁止

### テンプレート

```markdown
# 顧客ヘルススコア追跡表: {チーム名}

| # | 企業名 | ヘルススコア | 最終対応日 | 次回アクション | 備考 |
|---|--------|------------|----------|--------------|------|
| CS-1 | {名称} | {Green/Yellow/Red} | {日付} | {アクション} | {特記} |

ヘルススコア凡例:
- Green: 正常（利用活発、CSAT良好、問い合わせ少）
- Yellow: 要注意（利用低下傾向、未回答サーベイ、問い合わせ増加）
- Red: 危険（利用停止、CSAT低下、チャーン兆候）
```
