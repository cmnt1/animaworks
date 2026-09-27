# Troubleshooting Flowchart

A flowchart for deciding whether to resolve a problem yourself or consult/report to someone when an issue occurs.

Refer to this document when you are unsure how to proceed. If the problem is clearly something you can resolve on your own, this flowchart is not needed.

---

## Decision Flowchart

When a problem occurs, work through the following steps in order.

### Step 1: Identify the Type of Problem

Classify the problem into one of the following categories:

| Type | Description | Example |
|------|------|----|
| **A. Technical Problem** | Issues related to the operation of tools or systems | Tool error, insufficient permission, missing file |
| **B. Operational Problem** | Issues related to how to proceed with a task or make decisions | Unclear specifications, priority decisions, blockers |
| **C. Interpersonal Problem** | Issues related to coordination with other Anima instances | No response, contradictory instructions, unclear ownership |
| **D. Urgent Problem** | Issues requiring immediate action | Risk of data loss, security concern |

### Step 2: Determine Urgency

| Urgency | Criteria | Response |
|--------|------|------|
| **High** | If left unaddressed, there is a risk of data loss or a security risk | MUST: Report to supervisor immediately |
| **High** | Other Anima instances' work is completely blocked | MUST: Report to supervisor immediately |
| **Medium** | Your own work is blocked, but you can start other tasks | SHOULD: Report to supervisor within 1 hour |
| **Low** | Work efficiency decreases, but progress is still possible | MAY: Report at the next heartbeat |

**If urgency is "High"** → Proceed to Step 5 (escalate immediately)

### Step 3: Attempt to Resolve on Your Own

Attempt to resolve the problem on your own using the following steps. If resolved at any step, stop there.

1. **Search your memory**
   ```
   search_memory(query="問題に関連するキーワード", scope="all")
   ```
   - Check whether you have experienced the same problem before
   - Check whether the procedure manual (procedures/）) contains a way to handle it
   - **If you want to recall what you just did** (recent tool results, email content, search results, etc.), try `scope="activity_log"`. Even with `scope="all"`, activity_log is merged via BM25 with RRF, but explicitly narrowing to activity_log tends to reduce noise

2. **Search shared knowledge**
   ```
   search_memory(query="問題に関連するキーワード", scope="common_knowledge")
   ```
   - Check whether `troubleshooting/common-issues.md` contains a relevant problem

3. **Consider an alternative approach**
   - Think about whether there is an alternative way to achieve the goal
   - If permission is insufficient, try another route; if there is a tool error, try another tool

4. **Time limit for self-resolution**
   - Technical problem: escalate if not resolved within 15 minutes
   - Operational problem: escalate immediately if unsure (avoid the risk of making the wrong decision)
   - Interpersonal problem: escalate after one retry

### Step 4: Determine the Escalation Target

| Type of Problem | Who to Consult First | If Consultation Does Not Resolve It |
|-----------|----------------|----------------------|
| **A. Technical Problem** | Colleague (if in the same specialty) | Supervisor |
| **B. Operational Problem** | Supervisor | ― |
| **C. Interpersonal Problem** | Supervisor (request mediation) | ― |
| **D. Urgent Problem** | Supervisor (immediately) | ― |

**Decision criteria:**
- Conditions for consulting a colleague: the colleague shares the same supervisor and the problem is related to their specialty
- Conditions for MUST report to supervisor: operational judgment is required, other departments are involved, or urgency is high
- Do not contact Anima instances in other departments directly (MUST: go through the supervisor)

### Step 5: Execute the Escalation

The report message MUST include the following elements:

1. **Situation**: What is happening
2. **Cause**: What is considered to be the cause (if unknown, write "cause under investigation")
3. **Attempts**: What you have tried on your own
4. **Request**: What you want the supervisor to do (judgment, permission grant, mediation, etc.)

**send_message constraints (implementation-compliant)**:
- `intent` is MUST: either `report` (report) or `question` (question). Cannot be omitted. `intent="delegation"` is **rejected** (task delegation is only possible via `delegate_task`)
- Acknowledgment, thanks, and FYI cannot be sent via DM. Use Board (post_channel) instead
- The number of DM recipients per run is limited by the role-specific setting in /status.json (general/ops is 2 people, engineer is 5 people, manager is 10 people, etc.). Only one message per recipient. If the limit is exceeded, use Board
- DM and Board **share the same outbound budget** (with per-hour and per-24-hour limits). See `communication/sending-limits.md` for details
- **Recipient**: Anima name, or a human alias (if configured in config, external delivery is made to Slack/Chatwork etc.)
- **During chat**: Replies to human users are made directly as text. `send_message` is used only for other Anima instances (or externally via configured aliases)
- **Contacting humans** (destinations not reachable via `send_message`, such as when no alias is set): If you are a top-level Anima and notification settings are enabled, use `call_human` (see below)
- When replying in a thread, specify `reply_to` and `thread_id` to maintain context
- If urgency is "High" and immediate human response is needed, consider `call_human` (`subject`, `body`, `priority`)

**post_channel (Board) constraints** (used when communicating to 3 or more people):
- Channels without metadata (general, ops, etc.) are available to everyone. Member-only channels can only be posted to by members (ACL). If you do not have access, you can check members via `manage_channel(action="info", channel="チャネル名")`
- Only one post per run per channel. Repeated posts to the same channel require a cooldown (`heartbeat.channel_post_cooldown_s` in `config.json`, default 300 seconds)
- You can mention people in the body using `@名前`. Mentioned recipients receive a DM notification

**call_human and the human notification infrastructure (`core/notification/` implementation-compliant)**:

- **Tool availability condition**: `human_notification.enabled` in `config.json` is true, and `HumanNotifier.from_config` has **actually built one or more send channels** (only `enabled: true` among `channels[]` and registered `type` are targeted. `enabled: false` is skipped, unregistered `type` is skipped with a warning log)
- **Top-level only (supervisor gate)**: If `config.animas` **contains an entry for that Anima name** and `supervisor` is non-null, `HumanNotifier` is not granted and `call_human` cannot be used (subordinates escalate to their supervisor via `send_message`). **An Anima not registered in `animas` does not pass through this gate**, so theoretically `call_human` could be assigned with only a notification channel. In operation, it is safe to explicitly list all Anima instances in `animas` so that only `supervisor: null` has human notifications
- **Send method**: **Parallel sending** to each channel where `HumanNotifier.notify` is valid (`asyncio.gather(..., return_exceptions=True)`). Each channel returns a success string or a failure string containing `ERROR`; **an exception in one channel is swallowed and the others continue**
- **Supported channel types** (`human_notification.channels[].type`): `slack`, `chatwork`, `line`, `telegram`, `ntfy` (corresponding to `@register_channel` in `core/notification/channels/*.py`). Multiple channels can be defined in parallel
- **Parameters**: `subject` and `body` are required. `priority` is optional. Enumeration is `low` / `normal` / `high` / `urgent` (default `normal` when omitted). **Strings outside `PRIORITY_LEVELS` are normalized to `normal` within `HumanNotifier.notify`**
- **How priority is displayed**:
  - **Slack / Chatwork / LINE / Telegram**: When `high` / `urgent`, **`[HIGH]` / `[URGENT]`** is prepended (`priority.upper()`). Not added for `low` / `normal`
  - **ntfy**: Set `low=2`, `normal=3`, `high=4`, `urgent=5` in the HTTP header `Priority`. The body is the request body (max approximately 4096 characters), with the subject in the `Title` header plus `(from Anima名)` if needed
- **Slack** (`channels/slack.py`):
  - **Bot Token + `channel`** (`chat.postMessage`) or **Incoming Webhook**. The body is formatted for Slack via `md_to_slack_mrkdwn`
  - **If Bot and `anima_name` exist**: The Anima name is passed to the API's `username`, so **do not add `(from Anima名)` in the body** (in Webhook mode, `(from Anima名)` is added to the body). If the configuration and assets are in place, `icon_url` can also be added
  - **Thread reply routing** (`reply_routing.py`): Only when posting as a Bot, `anima_name` is not empty, and the API response contains `ts`, save to `notification_map.json`. The path is `{data_dir}/run/notification_map.json` (usually `~/.animaworks/run/`). Entries are discarded **after a maximum of 7 days** from creation. Webhook cannot obtain `ts` and cannot be mapped
  - When routing, try to fetch the thread summary via the Slack API if possible; on failure, fall back to a summary of the saved notification text. External messages to the Inbox are `intent="question"`
- **Chatwork**: `room_id` allows **numeric values only**. The body is converted via `md_to_chatwork` and formatted as `[info][title]…[/title]…[/info]`
- **LINE**: Push API. Text is truncated to a maximum of 5000 characters
- **Telegram**: `parse_mode=HTML`. The subject is `<b>…</b>`, and the total is adjusted to within 4096 characters (truncated after escaping)
- **Credentials**: The base `NotificationChannel._resolve_credential_with_vault` is **configuration key env → `{キー}__{anima_name}` (vault/shared）→ raw key** in that order. Slack Bot additionally has a fallback via `get_credential("slack", "notification", …)` (see each `channels/*.py`)
- **Chat UI**: A **`notification_sent`** event is sent with streaming responses (via `core/anima/messaging.py`; a separate path from external channels)
- **Logging**: When `call_human` is executed, **`human_notify`** is written to the unified activity log (`via` is fixed in the implementation as `configured_channels`). `tool_result` is also recorded. Priming's "Pending Human Notifications" aggregates **up to 10 items from the past 24 hours** of `human_notify` (`core/memory/priming/outbound.py`)
- **Other HumanNotifier uses**: There is a path where the framework sends to humans via **the same `HumanNotifier`** for background tool completions, etc. (other than the `call_human` tool. The same restriction to top-level Anima applies)
- **Mode S (CLI)**: The same type of notification can be sent via `animaworks-tool call_human "件名" "本文" [--priority …]`

**call_human parameters (summary)**:
- `subject` and `body` are required. `priority` is optional (`low` / `normal` / `high` / `urgent`, default `normal`. Invalid values are treated as `normal`)

---

## Escalation Message Templates

### Template 1: Blocked Report

```
send_message(
    to="上司の名前",
    content="""【ブロック報告】

■ 状況
タスク「月次レポート作成」がブロックされています。

■ 原因
売上データが格納されている /data/sales/ ディレクトリへの読み取り権限がありません。

■ 試行済み
- permissions.json を確認 → /data/sales/ は未許可
- 代替データソースを検索 → 該当なし

■ 依頼
/data/sales/ への読み取り権限の追加をお願いします。""",
    intent="report"
)
```

### Template 2: Judgment Request

```
send_message(
    to="上司の名前",
    content="""【判断依頼】

■ 状況
タスク「顧客対応フロー改善」で2つの方針が考えられます。

■ 選択肢
A案: 既存フローを段階的に修正（工数: 小、リスク: 低、効果: 中）
B案: フローを全面刷新（工数: 大、リスク: 中、効果: 高）

■ 私の見解
A案を推奨します。理由: 現行フローの問題点は限定的であり、段階的修正で十分対応可能なため。

■ 依頼
方針の決定をお願いします。""",
    intent="question"
)
```

### Template 3: Technical Consultation with a Colleague

```
send_message(
    to="同僚の名前",
    content="""【技術相談】

Slack APIの rate limit に引っかかっています。

■ 状況
- 100件以上のメッセージを一括送信しようとしている
- 50件目あたりで 429 Too Many Requests が返される

■ 質問
Slack API の rate limit 回避策について知見はありますか？
バッチ処理の間隔を空ける方法を検討していますが、適切な間隔がわかりません。""",
    intent="question"
)
```

### Template 4: Urgent Report

If urgency is "High" and immediate human response is needed, also use `call_human` (the tool is only available to **top-level Anima** instances and when `human_notification` is valid. Subordinate Anima instances should limit themselves to `send_message` to their supervisor).

```
send_message(
    to="上司の名前",
    content="""【緊急報告】

■ 状況
外部API（XXXサービス）から認証エラーが継続的に発生しています。

■ 影響
- YYYタスクが完全に停止
- ZZZタスクも同じAPIを使用しており影響の可能性あり

■ 試行済み
- リトライ3回実施 → すべて失敗
- APIキーの有効性は自分では確認できない

■ 依頼
APIキーの確認と、影響範囲の調査をお願いします。""",
    intent="report"
)
```

If immediate human notification is needed:
```
call_human(
    subject="【緊急】外部API認証エラー継続発生",
    body="XXXサービスから認証エラーが継続しています。YYYタスク停止中。APIキー確認をお願いします。",
    priority="urgent"
)
```

---

## Common Escalation Scenarios

### Scenario 1: Unclear Instructions

**Situation**: You were instructed by your supervisor to "create a report," but the target period, format, and submission destination are unclear.

**Correct response**:
1. Organize what you can reasonably infer on your own
2. Ask specific questions about the unclear points

```
send_message(
    to="上司の名前",
    content="""レポート作成の件、以下を確認させてください。

1. 対象期間: 今月分でよろしいでしょうか？
2. フォーマット: 前回と同じMarkdown形式でよろしいでしょうか？
3. 提出先: knowledge/ に保存でよろしいでしょうか？

上記で問題なければ着手します。""",
    intent="question"
)
```

**What not to do**:
- Proceed with your own interpretation without confirming
- Reply only with "the instructions are unclear" (without specific questions)
- Omit `intent` in `send_message` (either `report` or `question` is required. Omitting it will cause an error)### Scenario 2: Conflicting instructions from multiple supervisors

**Situation**: Your direct supervisor tells you to "prioritize A," but another Anima asks you to "do B first."

**Correct response**:
1. Prioritize the direct supervisor's instruction (MUST)
2. Report the situation to your direct supervisor

```
send_message(
    to="直属の上司の名前",
    content="""【優先順位の確認】

現在タスクAに着手中ですが、XXXさんからタスクBの優先依頼がありました。
指示通りタスクAを優先して進めますが、問題ないでしょうか？

タスクBの依頼内容: YYYの対応（XXXさんからの依頼）""",
    intent="question"
)
```

### Scenario 3: Repeated errors during work

**Situation**: Message sending to the Chatwork API has failed 3 times in a row.

**Correct response**:
1. Record the error details
2. If the issue is not resolved after 3 retries, escalate it
3. Start on other tasks that are not blocked

```
# エラーを記録
write_memory_file(
    path="state/current_state.md",
    content="## ブロック中\n\nChatwork API連続エラー\n- 1回目: 10:00 - 500 Internal Server Error\n- 2回目: 10:05 - 500 Internal Server Error\n- 3回目: 10:10 - 500 Internal Server Error\n\n上司に報告済み。他タスクに着手中。",
    mode="overwrite"
)

# 上司に報告
send_message(
    to="上司の名前",
    content="【ブロック報告】Chatwork APIが3回連続で500エラーを返しています。外部障害の可能性があります。復旧を待ちつつ、他のタスクに着手します。",
    intent="report"
)
```

### Scenario 4: Discovering a problem outside your scope of responsibility

**Situation**: During your work, you discover an inconsistency in data managed by another Anima.

**Correct response**:
1. Record what you found
2. Report it to your direct supervisor (do not contact the Anima in another department directly)

```
send_message(
    to="上司の名前",
    content="""【情報共有】

作業中に以下の不整合を発見しました。私の担当外ですが共有します。

■ 発見内容
/data/reports/monthly.md の売上合計と /data/sales/summary.md の値が一致しません。
- monthly.md: 1,234,567円
- summary.md: 1,234,000円

■ 発見経緯
月次レポート作成中にデータ参照した際に気づきました。

対応の要否はお任せします。""",
    intent="report"
)
```

---

## Checklist when you are unsure how to proceed

Escalate with MUST if any of the following apply:

- [ ] A wrong decision here would have irreversible consequences
- [ ] The operation requires going beyond your scope of permission
- [ ] It affects an Anima in another department
- [ ] No solution has been found after 15 minutes
- [ ] The same issue has occurred more than once
- [ ] It involves security or data safety

You MAY attempt to resolve it on your own if any of the following apply:

- [ ] You have solved a similar problem before
- [ ] The procedure manual (procedures/）) describes how to handle it
- [ ] Shared knowledge (common_knowledge/）) contains a solution
- [ ] It can be completed within your scope of permission
- [ ] The impact of failure is limited