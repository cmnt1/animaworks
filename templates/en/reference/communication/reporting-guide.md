# Reporting and Escalation Methods

> **Required**: Before reporting or escalating, check the required items in `communication/message-quality-protocol.md`.

Reporting to your supervisor is the lifeline of organizational operations.
Reporting at the right time and in the right format supports early problem detection and rapid decision-making.

## ツールの使い分け

報告には `send_message` ツールを使用する。以下の制約を守ること。

| ツール | 用途 | 備考 |
|--------|------|------|
| `send_message` | 上司・同僚への1対1報告・質問 | 報告・進捗・判断依頼は `intent="report"`、質問は `intent="question"`。Anima 名・エイリアス・`slack:`/`chatwork:` 等（下記参照） |
| `post_channel` | チーム全体へのお知らせ（Board） | acknowledgments・感謝・FYI は Board を使用。同一チャネル1回/run、再投稿はクールダウン（`heartbeat.channel_post_cooldown_s`、既定300秒）が必要 |
| `call_human` | 人間への緊急通知 | サービス停止・セキュリティインシデント等 |

**send_message の制約**:
- `intent` は必須で、値は **`report` または `question` のみ**（報告・進捗は `report`、質問は `question`）。**`delegation` は `send_message` では使えない**（ツールが拒否する）。タスク委譲は `delegate_task` を使う
- 1 run あたりの宛先数は **`max_recipients_per_run`**（`status.json` で上書き可、未設定時はロール既定。例: `general` は 2）。同一宛先へは 1 通のみ。3人以上への伝達は Board を使用
- 追加の連絡は Board（post_channel）を使用する
- **宛先** は下記「宛先の解決」を参照（Anima 名・人間エイリアス・`slack:` / `chatwork:` 直指定など）
- **注**: チャットセッション中は人間宛てに send_message は使えない。直接テキストで返答する

### Recipient Resolution and External Delivery (`core/messaging/outbound.py`)

The `to` of `send_message` is resolved to an internal inbox or external (Slack / Chatwork) using the following **priority order**. An empty string cannot be resolved and results in an error.

1. **Exact match with a known Anima name** (case-sensitive) → internal inbox. Known names are listed as directory names under `~/.animaworks/animas/`
2. **Match with a key in `external_messaging.user_aliases` of `config.json`** (aliases are **case-insensitive**) → external delivery. If `slack` is set for `external_messaging.preferred_channel` (`slack` / `chatwork`), use Slack if `slack_user_id` exists, otherwise use Chatwork if `chatwork_room_id` exists. If `chatwork` is set for `preferred_channel`, prioritize `chatwork_room_id`; if absent, use Slack if `slack_user_id` exists. **Aliases with neither ID** result in an error (set contact information in `external_messaging.user_aliases`)
3. **`slack:USERID`** (starts with `slack:`, followed by a Slack user ID) → direct Slack DM (USERID is **normalized to uppercase** in implementation)
4. **`chatwork:ROOMID`** (starts with `chatwork:`, ROOMID portion only has leading/trailing whitespace removed) → direct Chatwork room
5. **Slack user ID alone** (`U` + alphanumeric **8 or more characters**, case tolerance allowed at match time. Example: `U0123456789`) → direct Slack DM
6. **Case-insensitive match with a known Anima name** → internal (normalized to the canonical name on disk)
7. **No match** → unknown recipient error (the tool layer may switch hint wording depending on whether a chat is running)

**External configuration** (`external_messaging` of `config.json`):

| Field | Role |
|-----------|------|
| `preferred_channel` | Default channel for alias delivery (`slack` / `chatwork`) |
| `user_aliases` | Alias name → `{ "slack_user_id": "...", "chatwork_room_id": "..." }` (**at least one** is required) |

**External send behavior** (`send_external`):

- Attempt order: **try the resolved channel first**, then try **the other channel** on failure (a second channel exists only when both Slack and Chatwork destination IDs are available, e.g., via aliases. Direct specification of `slack:` / `chatwork:` usually targets only that channel)
- If sending to an external channel fails (e.g., channel not configured), the tool result may return `NoChannelConfigured` or `DeliveryFailed` as JSON
- Body text is converted from **Markdown to Slack mrkdwn / Chatwork format**
- **Slack**: If a `SLACK_BOT_TOKEN__{anima名}` associated with the Anima name (from Vault or shared credentials) exists, send with the Bot token, attaching the display name (Anima name) and **icon URL** (from Anima assets). **If no Bot token exists**, prepend `[送信者Anima名] ` to the message body
- **Chatwork**: Uses the sending Anima's own identity token (`CHATWORK_API_TOKEN__<Anima名>`). When sent via `send_message`, a `[Anima名] ` prefix is added to the message body

**Send limits (based on implementation)**:

- **Global (time window)**: `send_message` to internal Animas (via `Messenger.send`) and **`post_channel` share the same send count**. Determined by `dm_sent` / `message_sent` / `channel_post` in the last 1 hour and 24 hours on `activity_log`. The limit is **`max_outbound_per_hour` / `max_outbound_per_day` from `status.json`** if available; otherwise, **role-specific defaults** apply (e.g., `general` is 15/hour and 50/day, `manager` is 60/hour and 300/day). When exceeded, sending is blocked; per the tool result, save the content to `current_state.md` etc. and send it in the next session
- **Same pair (internal Anima DM only)**: Within the `heartbeat.depth_window_s` window (default 600 seconds = 10 minutes), up to `heartbeat.max_depth` (default 6 turns). When exceeded, sending to the other party is blocked (wait until the next window)

## Reporting Timing

### Situations Requiring Immediate Reporting (MUST)

Report immediately upon recognition in the following situations:

| Situation | Reason | Example |
|------|------|-----|
| Task completion | So the supervisor can decide the next action | Deployment complete, report created |
| Error or failure occurrence | For early response | API outage, data inconsistency detected |
| Decision needed | To seek approval beyond your authority | Policy change proposal, resource addition request |
| Deadline delay is certain | So the supervisor can adjust the schedule | Work halted due to a blocker |
| Security concern | Requires immediate action | Signs of unauthorized access, suspected credential leak |

### Regular Reporting Situations (SHOULD)

| Situation | Frequency | Content |
|------|------|------|
| Daily summary | Every day (at end of work) | Day's achievements and next day's plans |
| Weekly review | Every week (Friday) | Week's achievements, issues, and next week's plans |
| Long-term task progress updates | As appropriate (roughly every 2-3 days) | Progress rate, remaining work, presence of blockers |

### Situations Where Reporting Is Not Needed

- Memory writes and organization (internal work)
- Routine work with no anomalies (equivalent to `HEARTBEAT_OK` via heartbeat)
- Work that the supervisor has explicitly said requires no reporting

## Basic Report Format

### SCANA Format

Reports consist of the following five items. Not all items need to be included; select as appropriate for the situation.

| Item | English | Description | MUST/MAY |
|------|------|------|----------|
| Situation | Situation | What is currently happening | MUST |
| Cause | Cause | Why it happened (if known) | MAY |
| Action taken | Action taken | What you have done | SHOULD |
| Next steps | Next steps | What you will do next / what decision you need | MUST |
| Appendix | Appendix | Related logs, file paths, numbers | MAY |

### Thread Continuation in Replies

When replying to a message from your supervisor, specify `reply_to` (reply-to message ID) and `thread_id` (thread ID) to maintain conversation context. The ID format is `YYYYMMDD_HHMMSS_ffffff` (example: `20260215_093000_123456`).

```
send_message(
    to="manager",
    content="承知しました。15時までに対応します。",
    intent="report",
    reply_to="20260215_093000_123456",
    thread_id="20260215_090000_000000"
)
```

### Format Usage Example

```
send_message(
    to="manager",
    content="""【完了報告】売上データ月次集計

状況: 2026年1月の売上データ集計が完了しました。
対処: 部門別・カテゴリ別に集計し、前月比も算出しました。
次のステップ: 特にアクション不要です。レポートをご確認ください。
付加情報: /shared/reports/sales_summary_202601.md""",
    intent="report"
)
```

## Templates by Report Type

### Completion Report

Report when a task has completed successfully.

```
send_message(
    to="manager",
    content="""【完了報告】{タスク名}

状況: {タスク名}が完了しました。
成果物: {ファイルパスまたは結果の要約}
所要時間: {かかった時間}
備考: {特記事項があれば}""",
    intent="report"
)
```

**Concrete example:**

```
send_message(
    to="manager",
    content="""【完了報告】API仕様書のv2.1更新

状況: API仕様書にv2.1の変更点を反映しました。
成果物: /shared/docs/api-spec.md（差分: セクション3.2, 4.1を更新）
所要時間: 約45分
備考: ページネーションの例を3パターン追加しました。""",
    intent="report"
)
```

### Error Report

Report when a failure or error has occurred.

```
send_message(
    to="manager",
    content="""【エラー報告】{何が起きたか}

状況: {現在の状態の説明}
原因: {判明している範囲での原因}
影響範囲: {何が止まっているか、誰に影響しているか}
対処: {自分が試した対策とその結果}
次のステップ: {今後の対応案 / 判断が必要なこと}""",
    intent="report"
)
```

**Concrete example:**

```
send_message(
    to="manager",
    content="""【エラー報告】定期バッチ処理の失敗

状況: 毎朝9:00のデータ同期バッチが3回連続で失敗しています。
原因: 外部APIのレスポンスタイムアウト（30秒超過）。API側の障害の可能性が高い。
影響範囲: 今朝以降のデータが未同期。ダッシュボードの数値が昨日時点で止まっている。
対処: タイムアウトを60秒に延長して再実行 → 同様に失敗。API提供元のステータスページを確認 → メンテナンス情報なし。
次のステップ: API提供元への問い合わせが必要です。ご判断をお願いします。""",
    intent="report"
)
```

### Decision Request (Escalation of Decision-Making)

Report when a decision is beyond your authority.

```
send_message(
    to="manager",
    content="""【判断依頼】{何について判断が必要か}

状況: {現在の状況}
選択肢:
A. {選択肢Aの内容} — メリット: {利点} / デメリット: {欠点}
B. {選択肢Bの内容} — メリット: {利点} / デメリット: {欠点}
私の推奨: {A or B}（理由: {なぜ}）

ご判断をお願いします。""",
    intent="report"
)
```

**Concrete example:**

```
send_message(
    to="manager",
    content="""【判断依頼】ログ保存期間の変更

状況: ディスク使用量が85%に達しており、1週間以内に90%を超える見込みです。
選択肢:
A. ログ保存期間を90日→30日に短縮 — メリット: 即座に50GB削減 / デメリット: 古いログでの調査が不可能に
B. ストレージを追加（500GB） — メリット: ログを維持できる / デメリット: 月額コスト増（約$50/月）
C. 古いログをアーカイブストレージに移動 — メリット: ログ維持+コスト抑制 / デメリット: 実装に2日必要
私の推奨: C（コストとデータ保全のバランスが良い）

ご判断をお願いします。""",
    intent="report"
)
```

### Progress Report

Intermediate report for long-term tasks.

```
send_message(
    to="manager",
    content="""【途中経過】{タスク名}

進捗: {完了した作業 / 全体に対する進捗率}
残作業: {まだ終わっていないこと}
ブロッカー: {あれば記載。なければ「なし」}
見込み: {期限に間に合うか}""",
    intent="report"
)
```

**Concrete example:**

```
send_message(
    to="manager",
    content="""【途中経過】ユーザー通知機能の実装

進捗: Phase 1（設計）完了、Phase 2（実装）の70%が完了
  - メール通知: 完了
  - Slack通知: 完了
  - アプリ内通知: 実装中（残り1日程度）
残作業: アプリ内通知の実装 + テストコード作成
ブロッカー: なし
見込み: 期限（2/20）に間に合います。""",
    intent="report"
)
```

## Daily Summary Format

The daily summary is a review of the day sent to your supervisor at the end of work.

### Template

```
send_message(
    to="manager",
    content="""【日次サマリー】2026-02-15

■ 完了したこと
- {完了タスク1}
- {完了タスク2}

■ 進行中
- {進行中タスク1}（進捗: {XX%}、見込み: {期限}）

■ 課題・懸念
- {あれば記載}

■ 明日の予定
- {予定1}
- {予定2}""",
    intent="report"
)
```

### Concrete Example

```
send_message(
    to="manager",
    content="""【日次サマリー】2026-02-15

■ 完了したこと
- API仕様書のv2.1更新（/shared/docs/api-spec.md）
- ログ監視スクリプトのバグ修正（タイムゾーン処理）

■ 進行中
- ユーザー通知機能の実装（進捗: 70%、見込み: 2/20完了予定）

■ 課題・懸念
- 外部APIのレスポンスが遅くなっている兆候あり（現時点では影響なし、引き続き監視）

■ 明日の予定
- アプリ内通知の実装完了
- テストコード作成着手""",
    intent="report"
)
```

## Deciding Between Urgent and Normal Reports

### Urgent Report (Immediate, MUST)

If any of the following apply, report immediately even if it means interrupting other work:

- **Service outage**: An outage affecting users
- **Data loss or corruption**: Potential for an unrecoverable state
- **Security incident**: Suspected unauthorized access or information leak
- **Confirmed deadline delay**: Certain that an already committed deadline will be missed

Urgent report messages MUST: prefix with "【緊急】" at the beginning.
If human immediate response is needed (service outage, data loss, security incident), also use `call_human`.

```
send_message(
    to="manager",
    content="""【緊急】本番データベースの応答遅延

状況: 本番DBの応答時間が通常の10倍（平均300ms→3000ms）に悪化。
影響: Web UIのページ読み込みが10秒以上かかる状態。
対処中: スロークエリの特定を開始。10分以内に続報します。""",
    intent="report"
)
```

### Normal Report (At the Next Heartbeat or Daily Summary)

The following are low urgency and can be reported together:

- Progress on tasks proceeding as planned
- Minor issues already resolved by yourself
- Improvement suggestions or ideas

## Escalation Decision Flowchart

Procedure for deciding whether a report should be escalated:

```
1. 自分の権限内で解決可能か？
   → Yes: 自分で対処し、完了後に結果を報告
   → No: ステップ2へ

2. 緊急性はあるか？（サービス影響・データ損失リスク）
   → Yes: 【緊急】として即座にエスカレーション
   → No: ステップ3へ

3. 判断の選択肢を整理できるか？
   → Yes: 選択肢と推奨を添えて【判断依頼】として報告
   → No: 状況をありのまま報告し、上司の指示を仰ぐ
```

## Reporting Precautions

### Things to Do (MUST/SHOULD）

- MUST: Specify **`"report"` (report, progress) or `"question"` (question)** for `intent` of `send_message`. `"delegation"` is not allowed (use `delegate_task` for delegation)
- MUST: Distinguish facts from speculation. Add "highly likely" or "probably" for speculation
- MUST: Clearly state the scope of impact. What is affected and who is affected
- SHOULD: Include the measures you tried and their results. Avoid the supervisor proposing the same measures
- SHOULD: Propose the next action yourself. Do not wait for instructions

### Things to Avoid

- Writing a long background before getting to the conclusion (put the conclusion first)
- Reporting "a problem occurred" without any specific information
- Combining multiple different topics into one message (separate by topic)
- Hiding problems or making them seem minor (convey the accurate situation)
- Sending send_message to the same recipient more than once in the same run (limit to one message; use Board for additional communication). Also, DMs cannot be sent to more than `max_recipients_per_run` people