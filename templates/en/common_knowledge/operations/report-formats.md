# Report Format Collection

Standard reporting templates and checklists used by each role.

## Manager: Status Report

```markdown
## 状況報告

### 完了事項
- [完了したタスクと成果]

### 進行中
- [タスク名]: [進捗率/状態] — [次のステップ]

### 課題・リスク
- [課題の内容と影響度] — [対応方針]

### 判断が必要な事項
- [判断を仰ぎたい内容と選択肢]
```

## Researcher: Research Report

```markdown
# 調査レポート: [テーマ]

## 概要
[1-3文で調査結果のサマリ]

## 調査目的
[何を明らかにしようとしたか]

## 調査方法
[どのように調べたか — 検索キーワード、参照先]

## 発見事項
### 主要な発見
- [箇条書きで列挙]

### 詳細
[各発見事項の詳細説明]

## 情報源と信頼度
| ソース | 種別 | 信頼度 |
|--------|------|--------|
| [URL/名前] | [公式/一次/二次] | [高/中/低] |

## 結論と推奨
[調査結果に基づく判断と次のアクション]
```

## Operations: Periodic Monitoring Report

```markdown
## 定期監視レポート

### 確認時刻
[YYYY-MM-DD HH:MM]

### システム状態
- [対象]: [正常/注意/異常] — [補足]

### リソース状況
- ディスク: [使用率]%
- メモリ: [使用率]%

### 直近のイベント
- [イベントの要約]

### 対応事項
- [対応が必要な場合の内容]
```

## Operations: Incident Record

```markdown
## インシデント記録

- 発生時刻: [YYYY-MM-DD HH:MM]
- 検知方法: [heartbeat/cron/手動]
- 重大度: [P1-P4]
- 影響範囲: [具体的な影響]
- 原因: [判明した原因 / 調査中]
- 対応内容: [実施した対応]
- 再発防止: [必要な対策]
```

## Writer: Self-Review Checklist

### Content
- [ ] Is the purpose clearly stated at the beginning?
- [ ] Are there any logical leaps?
- [ ] Is the level of explanation appropriate for the reader's prior knowledge?
- [ ] Is any necessary information missing?
- [ ] Is any unnecessary information included?

### Expression
- [ ] Are sentences too long? (Guideline: within 60 characters)
- [ ] Is there repetition of the same content?
- [ ] Are there too many passive constructions? (Prefer active voice)
- [ ] Can vague expressions (such as "etc." or "various") be made more specific?

### Format
- [ ] Is the heading hierarchy well organized?
- [ ] Is the granularity of bullet lists consistent?
- [ ] Do code blocks, links, and tables display correctly?
- [ ] Are there any typos or missing characters?