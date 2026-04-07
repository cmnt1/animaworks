# 経営企画フルチーム — チーム概要

## 3ロール構成

| ロール | 責務 | 推奨 `--role` | `speciality` 例 | 詳細 |
|--------|------|--------------|-----------------|------|
| **Corporate Strategist** | 戦略判断・事業環境分析（machine）・OKR管理・最終承認 | `manager` | `corporate-strategist` | `corporate-planning/strategist/` |
| **Business Analyst** | 市場/競合データ収集・構造化分析（machine） | `researcher` | `business-analyst` | `corporate-planning/analyst/` |
| **Strategy Coordinator** | 独立検証（machine）・部門横断調整・KPI追跡 | `administration` | `strategy-coordinator` | `corporate-planning/coordinator/` |

1つの Anima に全工程を集約すると、戦略判断のバイアス（楽観偏向）・施策の消失（silent drop）・コンテキスト肥大化が発生する。

各ロールディレクトリに `injection.template.md`（injection.md 雛形）、`machine.md`（machine 活用パターン）、`checklist.md`（品質チェックリスト）がある。

> 基本原則の詳細: `team-design/guide.md`

## ハンドオフチェーン

```
Analyst (トレンド・競合・市場データ収集 → machine で構造化)
  → market-analysis.md → Strategist
    → Strategist → strategic-plan.md (approved)
      → machine で事業分析（勝てる領域の抽出）
        → strategy-report.md (reviewed)
          → Coordinator (独立検証[machine]: KPI実態との整合 + 実行可能性)
            └─ 指摘あり → Strategist に差し戻し
            └─ APPROVE → Strategist → Tracker 更新 → call_human → 人間が最終確認
```

### 引き継ぎドキュメント

| 送信元 → 送信先 | ドキュメント | 条件 | 通信手段 |
|----------------|------------|------|---------|
| Strategist → Analyst | 調査依頼 | | `delegate_task` |
| Analyst → Strategist | `market-analysis.md` | `status: approved` | `send_message (intent: report)` |
| Strategist → Coordinator | `strategy-report.md` | `status: reviewed` | `send_message (intent: report)` |
| Coordinator → Strategist | `verification-report.md` | `status: approved` | `send_message (intent: report)` |
| Coordinator → 各部門 | 施策伝達 | Strategist 承認後 | `send_message` |
| Strategist → COO / 上位 | 最終レポート | 全承認後 | `send_message (intent: report)` |

### 運用ルール

- **修正サイクル**: Critical → 全体再分析（Analyst に再調査 + Coordinator に再検証）/ Warning → 差分確認のみ / 3往復解消しない → 人間にエスカレーション
- **Tracker ルール**: Strategic Initiative Tracker の全項目を次回レビュー時に更新する。silent drop（言及なしでの消滅）は禁止
- **machine 失敗時**: `current_state.md` に記録 → 次回 heartbeat で再評価

## スケーリング

| 規模 | 構成 | 備考 |
|------|------|------|
| ソロ | Strategist が全ロール兼務（checklist で品質担保） | 単一プロジェクトの戦略レビュー |
| ペア | Strategist + Coordinator | 検証の独立性を確保したい場合 |
| フルチーム | 本テンプレート通り3名 | フル戦略サイクル（調査→分析→検証→実行追跡） |
| スケールド | Strategist + 複数 Analyst（領域別）+ Coordinator | 複数事業領域の同時分析 |

## 他チームとの対応関係

| 開発チームロール | 法務チームロール | 経営企画チームロール | 対応する理由 |
|----------------|----------------|---------------------|-------------|
| PdM（調査・計画・判断） | Director（分析計画・判断） | Strategist（戦略判断） | 「何をやるか」を決定する司令塔 |
| Engineer（実装） | Director + machine（契約書スキャン） | Strategist + machine（事業分析） | machine で分析を実行 |
| Reviewer（静的検証） | Verifier（独立検証） | Coordinator（独立検証） | 「実行と検証の分離」の核。machine でバイアスなき検証 |
| Tester（動的検証） | Researcher（根拠検証） | Analyst（データ収集・分析） | 外部データで裏付けを取る |

## Strategic Initiative Tracker — イニシアチブ追跡表

イニシアチブの進捗を追跡し、silent drop を構造的に防止する。

### 追跡ルール

- 新しいイニシアチブが発生したらこの表に登録する
- 次回レビュー時に全項目のステータスを更新する
- 停滞（1ヶ月以上ステージ変化なし）は Strategist に報告する
- silent drop（言及なしでの消滅）は禁止

### テンプレート

```markdown
# イニシアチブ追跡表: {チーム名}

| # | イニシアチブ | オーナー | ステージ | 開始日 | 期限 | 備考 |
|---|------------|---------|---------|--------|------|------|
| SI-1 | {名称} | {部門/名前} | {ステージ} | {日付} | {日付} | {特記} |

ステージ凡例:
- 企画中: 戦略検討中
- 承認済み: 実行開始待ち
- 実行中: 施策進行中
- レビュー: 効果測定中
- 完了: 目標達成
- 中止: 理由を備考に記録
```

## cron 設定例

| タスク | schedule 例 | type | 概要 |
|--------|------------|------|------|
| 月次レビュー | `0 10 1 * *` | llm | Tracker 全件レビュー + 進捗分析 |
