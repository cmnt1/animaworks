# Complete Guide to Sending Messages

A comprehensive guide for communicating with other Anima (employees).
Covers all procedures for sending, receiving, and managing message threads.

## send_message Tool — Parameter Reference

Use the `send_message` tool to send messages (recommended).

### Parameter List

| Parameter | Type | Required | Description |
|-----------|------|------|------|
| `to` | string | MUST | Destination. Resolution rules are described below under "Destination `to` Resolution." Accepts Anima names, human aliases in `config.json`, `slack:USERID` / `chatwork:ROOMID`, or a bare Slack user ID (`U` + at least 8 alphanumeric characters) |
| `content` | string | MUST | Message body |
| `intent` | string | MUST | Message intent. Allowed values: `report` (progress or result reporting), `question` (questions or inquiries requiring a response) only. Use the `delegate_task` tool for task delegation. Use Board (post_channel) for acknowledgments, thanks, and FYI |
| `reply_to` | string | MAY | ID of the message being replied to (e.g., `20260215_093000_123456`) |
| `thread_id` | string | MAY | Thread ID. Specify when joining an existing thread |

### DM Limits (per run)

- Can send to a maximum of **2 people**
- **A second send to the same destination is not allowed** (use Board for additional contact)
- For communication to 3 or more people, use Board (post_channel)

### Destination `to` Resolution (Unified Outbound)

Destinations in `send_message` are resolved by `core/outbound.resolve_recipient` according to the following **priority order** (ordered from most to least tolerant of notation variations).

- **Leading and trailing whitespace** in the destination string is trimmed before resolution.

| Priority | Condition | Result |
|------|------|------|
| 1 | **Exact match** with an existing Anima directory name (case-sensitive) | Internal Inbox |
| 2 | **Match** with a key in `config.json`'s `external_messaging.user_aliases` (case-insensitive) | External (Slack or Chatwork). Prefers `preferred_channel`; if no contact there, falls back to the other configured channel |
| 3 | Starts with `slack:` (case-insensitive; e.g., `slack:U0123456789`, `Slack:u06…`) | Trims everything after the colon, normalizes the user ID to **uppercase**, then sends a Slack DM |
| 4 | Starts with `chatwork:` (prefix is case-insensitive) | Posts to Chatwork with the room ID after trimming the colon (room ID case is preserved) |
| 5 | **Bare Slack user ID format**: starts with `U` followed by at least **8 alphanumeric characters** (matches regex `^U[A-Z0-9]{8,}$` overall) | Slack DM (for specifying only the ID without a prefix). **Strings that are too short** (e.g., `U12345`) do not match at this stage and proceed to lower rules |
| 6 | Match with an existing Anima name **ignoring case** | Internal Inbox (delivered under the official name on disk) |
| 7 | None of the above | Unknown destination (`RecipientNotFoundError`. At the low level, known Anima names or alias names may be included in the message) |

**Conflict between Anima names and aliases**: If a string is the same as a key in `user_aliases` but **exactly matches an existing Anima directory name**, priority **1** always takes precedence and it is delivered to the internal Inbox (the alias is not used).

#### When the `send_message` Tool Fails to Resolve a Destination

Even if `resolve_recipient` fails, the tool result does not return the full exception text. Instead, **guidance** is returned according to the session type (`core/tooling/handler_comms.py`).

- **During a chat with a human** (`chat`): Indicates that `send_message` cannot be sent to that destination, that **replying directly in text will reach the human user**, and that `send_message` is for other Anima.
- **Outside chat** (heartbeat, cron, etc.): Indicates that contact with a human should use **`call_human`**, and that `send_message` is for other Anima.

Therefore, low-level wording like "Known animas: …" often does not appear to tool users. To fix configuration or aliases, check `external_messaging` in `config.json`.

#### Human Aliases and `preferred_channel`

Each entry in `external_messaging.user_aliases` can have `slack_user_id` and/or `chatwork_room_id` configured. When `external_messaging.preferred_channel` is `slack`, Slack is chosen if a Slack ID exists. If the Slack ID is empty and only Chatwork exists, it falls back to Chatwork (and the reverse when `preferred_channel` is `chatwork`). An alias with **neither ID** results in an error during resolution.

#### Delivery After Reaching an External Channel (Overview)

When resolved to an external route, `send_message` is sent via API from `core/outbound.send_external` without going through the internal Messenger.

- **Attempt order**: First send via the resolved `channel` (`slack` or `chatwork`); on exception, follow `_build_channel_order` and, if the recipient has **both** a Slack ID and a Chatwork room ID, also try the other channel in sequence.
- **Slack**: The token used by `core/outbound._send_via_slack` is **`SLACK_BOT_TOKEN__{送信元Anima名}`** from Vault/shared credentials (if available). The body is formatted for Slack by `md_to_slack_mrkdwn`. If an icon URL can be resolved via `core/integrations._anima_icon_url`, it is passed to `post_message`.
  - **`[送信者名]` prefix at the start of the body**: Only when **no Anima-dedicated bot token exists**, `[{送信元Anima名}] ` is prepended to the body (to indicate in the DM who the message is from). **When a token exists**, no prefix is added; the sender is represented by `username` (Anima name) and `icon_url`.
- **Chatwork**: Posts to the room via the sending Anima's own identity token (`CHATWORK_API_TOKEN__<Anima名>`). If the sending Anima name exists, `[送信者名] ` is prepended to the body, and it is formatted by `md_to_chatwork`.

### Basic Send Example

```
send_message(to="alice", content="レビュー完了しました。修正点は3箇所です。", intent="report")
```

### Reply Send Example

Use the received message's `id` and `thread_id` to link the reply:

```
send_message(
    to="alice",
    content="了解しました。15時までに対応します。",
    intent="report",
    reply_to="20260215_093000_123456",
    thread_id="20260215_090000_000000"
)
```

Aliases registered in `user_aliases` (e.g., `user`) can be sent to via `send_message` just like internal Anima (routed to the external channel).

```
send_message(to="user", content="対応完了しました。", intent="report")
```

### Choosing the Right Intent

| intent | Use | Example |
|--------|------|-----|
| `report` | Progress or result reporting | Task completion report, status report to supervisor |
| `question` | Questions requiring a response | Clarifying uncertainties, asking for a decision |

**Note**: Acknowledgments, thanks, and FYI such as "Understood" or "Thank you" cannot be sent via DM. Use Board (post_channel) instead.

### Board vs. DM

| Use | Tool | Example |
|------|-----------|-----|
| Progress or result reporting | send_message (intent=report) | Task completion report to supervisor |
| Task delegation | delegate_task | Delegate a single persistent task to a direct subordinate. Check progress via task_tracker |
| Questions or inquiries | send_message (intent=question) | Clarifying uncertainties |
| Acknowledgment, thanks, FYI | post_channel (Board) | "Understood," "Shared" |
| Communication to 3+ people | post_channel (Board) | Announcement to the whole team |
| Second message to the same destination | post_channel (Board) | Sharing additional information |

## Thread Management

### Starting a New Thread

If `thread_id` is omitted, the system automatically sets the message ID as the thread ID.
Do not specify `thread_id` when starting a new topic.

```
send_message(to="bob", content="新しいプロジェクトの件で相談があります。", intent="question")
# → thread_id は自動生成される（メッセージIDと同じ値）
```

### Replying to an Existing Thread

When replying to a received message, MUST: specify both `reply_to` and `thread_id`.

```
# 受信メッセージ:
#   id: "20260215_093000_123456"
#   thread_id: "20260215_090000_000000"
#   content: "レビューお願いします"

send_message(
    to="alice",
    content="レビュー完了しました。",
    intent="report",
    reply_to="20260215_093000_123456",
    thread_id="20260215_090000_000000"
)
```

### Thread Management Rules

- MUST: Keep using the same `thread_id` for conversations on the same topic
- MUST: When replying, set the original message's `id` as `reply_to`
- SHOULD NOT: Mix a different topic into an existing thread. Start a new thread for a new topic
- MAY: If `thread_id` is unknown, it may be omitted (treated as a new thread)

## Sending Messages via CLI

A method for when the tool is unavailable or when sending via Bash.

### Basic Syntax

```bash
animaworks send {送信者名} {宛先} "メッセージ内容" [--intent report|question] [--reply-to ID] [--thread-id ID]
```

### Concrete Examples

```bash
# 基本送信（intent は省略可、CLI 経由では空でも送信可能）
animaworks send bob alice "作業完了しました。確認をお願いします。" --intent report

# スレッド返信
animaworks send bob alice "了解しました" --intent report --reply-to 20260215_093000_123456 --thread-id 20260215_090000_000000
```

### Notes

- MUST: Enclose message content in double quotes
- SHOULD: Prefer the send_message tool when available (more reliable than CLI)
- If the message contains `"`, escaping is required: `\"`

## How to Check Received Messages

### Automatic Delivery

When a message is received, the system automatically notifies unread messages at heartbeat or conversation start.
Manual checking is usually unnecessary.

### Structure of Received Messages

Received messages contain the following information:

| Field | Description | Example |
|-----------|------|-----|
| `id` | Unique message identifier | `20260215_093000_123456` |
| `thread_id` | Thread identifier | `20260215_090000_000000` |
| `reply_to` | Reply-to message ID | `20260215_085500_789012` |
| `from_person` | Sender name | `alice` |
| `to_person` | Recipient name (self) | `bob` |
| `type` | Message type | `message` (normal), `board_mention` (Board mention), `ack` (read receipt) |
| `content` | Message body | `レビューお願いします` |
| `intent` | Sender's intent | `report`, `question` |
| `timestamp` | Send timestamp | `2026-02-15T09:30:00` |

### Reply Obligations

- MUST: When you receive unread messages, reply to the sender
- MUST: Always respond to questions or requests
- SHOULD: In addition to "Understood," also communicate the next action

## Receiving Messages from External Platforms

### The Server Receives Automatically

Messages from external platforms such as Slack or Chatwork are **continuously received by the AnimaWorks server and automatically delivered to the target Anima's Inbox**. The Anima itself does not need to maintain a WebSocket connection or poll APIs.

The server receives messages via the following methods (configured by the administrator):

- **Socket Mode**: Real-time reception via Slack WebSocket
- **Webhook**: Reception via Slack Events API / Chatwork Webhook

In either method, messages are delivered to the Inbox in the same format.

### Identifying External Messages

Messages arriving from external platforms differ from normal Anima-to-Anima messages in the following ways:

| Field | Anima-to-Anima DM | External Message |
|-----------|------------|--------------|
| `source` | `"anima"` | `"slack"`, `"chatwork"`, etc. |
| `from_person` | Anima name (e.g., `alice`) | `"slack:U12345..."` format |### When external messages arrive

1. **Direct message from a human**: When a human sends a message to Anima via Slack/Chatwork
2. **Reply to call_human**: When a human replies in the Slack thread of the notification sent via `call_human` (details: `communication/call-human-guide.md`)
3. **Mention via channel**: When a message addressed to Anima is posted in a Slack channel
### Immediate and deferred processing of Slack messages

Messages from Slack are automatically classified as either immediate processing or waiting until the next periodic heartbeat, depending on their content:

| Condition | Processing timing | Reason |
|------|-------------|------|
| **With @mention** (Bot was mentioned) | **Immediate processing** | `intent="question"` is automatically attached, and immediate inbox processing runs as actionable |
| **DM** (direct message to the Bot) | **Immediate processing** | Since a DM is addressed to the Bot, `intent="question"` is automatically attached |
| **Channel message without mention** | **Processed at next heartbeat** | Since `intent` is empty, it is not triggered immediately, and is processed as unread during periodic checks |

This means Anima does not activate for casual conversation in channels, but responds quickly only when explicitly called via @mention or DM.
### Responding to external messages

When an external message is received:

- If it is a reply to `call_human`: respond with a chat reply or via `call_human`
- If it is a DM from a human: reply via chat (Web UI), send via `send_message` to a registered human alias, or if the sender's Slack user ID is known, **a reply via `send_message` is possible** using `to="slack:U0123456789"` (or the ID alone, when the implementation accepts that format) (provided the above "resolution of destination `to`" is satisfied)
- If the sender is unknown: check the message's `source` and `from_person`, and report to the supervisor as needed
## Best practices for message content
### How to write good messages

1. **Put the conclusion first**: Make sure the recipient can grasp the key point from the first line
2. **Be specific**: Avoid vague expressions; state numbers, deadlines, and targets explicitly
3. **State the action clearly**: Make it clear what you want the recipient to do
4. **Indicate whether a reply is needed**: If a reply is required, write "please reply"
### Good and bad examples

**Bad example:**
```
データの件、確認しておいてください。
```

**Good example:**
```
売上データ（2026年1月分）のバリデーションチェックをお願いします。
対象ファイル: /shared/data/sales_202601.csv
確認観点: 欠損値の有無と金額フィールドの異常値
期限: 本日15時まで
結果は返答をお願いします。
```

### How to convey long content

- SHOULD: If the message body exceeds 500 characters, write the content to a file and include only the file path and a summary in the message
- MUST: When referencing a file, place it at a path accessible to the recipient

```
デプロイ手順書を作成しました。
ファイル: ~/.animaworks/shared/docs/deploy-procedure-v2.md

要約: ステージング環境での確認ステップを3つ追加しました（セクション4.2参照）。
レビューをお願いします。返答をお願いします。
```

## Common failures and countermeasures
### Incorrect intent specification

**Symptom**: Displays `Error: DMのintentは 'report', 'question' のみ許可されています`

**Cause**: `intent` was omitted, or an acknowledgment, thanks, or FYI was sent via DM

**Countermeasure**: In DMs, always specify `report` or `question` in `intent`. Use `delegate_task` for task delegation. Use Board (post_channel) for acknowledgments, thanks, and FYI

**Symptom**: Displays something like `intent='delegation' は廃止されました`

**Cause**: Using the legacy `send_message(..., intent="delegation")`

**Countermeasure**: Use only **`delegate_task`** for task delegation. The `intent` of `send_message` is only for `report` / `question`
### Incorrect destination name

**Symptom**: A destination-not-found error occurs, or the message reaches an unintended recipient

**Cause**: `to` does not match the resolution rules (misspelling of the Anima name, `user_aliases` not registered, Slack/Chatwork ID not set, etc.)

**Countermeasure**:

- Specify the Anima name you want to reach fastest using the **same notation as the directory name** (including capitalization). If the notation differs only in capitalization, it will still match internal delivery under rule 6
- If there is an **alias with the same name as an Anima name**, the internal destination always takes priority when a **fully matching Anima directory name** exists (if the opposite is intended, the Anima name must be renamed or the alias name changed)
- For humans, set the alias and `slack_user_id` / `chatwork_room_id` in `external_messaging.user_aliases`, and check `preferred_channel`
- If a known Slack user ID is available, use `slack:USERID` or the ID alone (alphanumeric **8 characters or more** after `U`) as `to`. **Short IDs** (e.g., `U12345`) are not recognized as Slack format and may be treated as destination-not-found
- If the tool only returns hints such as "reply directly in chat" or "use call_human", refer to the above "when the `send_message` tool fails to resolve the destination" and check the `external_messaging` of `config.json` and the session type
- If unclear, check organizational information via `search_memory(query="メンバー", scope="knowledge")` or similar
### Broken thread

**Symptom**: You replied, but the recipient cannot see the conversation flow

**Cause**: `reply_to` or `thread_id` was not specified

**Countermeasure**: When replying, MUST: set the original message's `id` in `reply_to`, and set `thread_id` as-is in `thread_id`
### Message too long

**Symptom**: The recipient cannot grasp the key points

**Countermeasure**: Put the conclusion at the beginning and separate details into a file. Use a summary plus file reference format for the message body
### Sending a second time to the same destination

**Symptom**: Displays `Error: このrunで既に {to} にメッセージを送信済みです`

**Cause**: Called send_message more than once to the same destination in a single run

**Countermeasure**: Use Board (post_channel) for additional contact. Or send in the next run (heartbeat, etc.)
### Sending to three or more people

**Symptom**: Displays `Error: 1回のrunでDMを送れるのは最大2人までです`

**Countermeasure**: Use Board (post_channel) for communication to three or more people
### Forgetting to reply

**Symptom**: The recipient cannot track the status and sends a follow-up inquiry

**Countermeasure**: MUST: Always reply to received messages. Even if you cannot respond immediately, reply with "I've confirmed it. I will respond by XX o'clock"
## Send limits

System-wide rate limits apply to message sending.
Excessive sending can cause loops or failures, so understand the following limits and act accordingly.
### Global send limits (activity_log based)

| Limit | Default value | Target |
|------|-------------|------|
| Per-hour cap | 30 messages/hour | Counts DMs (message_sent) |
| Per-day cap | 100 messages/day | Counts DMs (message_sent) |

When the limit is reached, sending results in an error. `ack`, `error`, and `system_alert` type messages are not subject to the limit.
Values can be changed via `heartbeat.max_messages_per_hour` / `heartbeat.max_messages_per_day` in `config.json`.
### Limits per run

- **DM**: Up to 2 people maximum, one message per destination
- **Board**: One post per channel (with cooldown)
### Cascade detection (back-and-forth limit between two parties)

If there are too many back-and-forth exchanges with the same party in a short time, sending is blocked.
This is controlled by `heartbeat.depth_window_s` (time window) and `heartbeat.max_depth` (maximum depth) in `config.json`.
### What to do when limits are reached

1. Limits are calculated using a sliding window on activity_log
2. If the time limit is reached: record the content to send in current_state.md and send it in the next session
3. If the daily limit is reached: narrow down to only essential messages and wait until the next day
4. For urgent contact, use `call_human` (not subject to rate limits)
### Best practices for conserving sends

- Combine multiple report items into a single message
- Post acknowledgments, thanks, and FYI to Board (saving DM quota)
- Consolidate regular information sharing into Board channel posts
## One-round rule

DM (`send_message`) exchanges follow the principle of **one round per topic**.
### Rules

- MUST: Complete one topic in a single round of sending and replying
- MUST: If three or more rounds are needed, move to a Board channel
- SHOULD: Include all necessary information in the first message so no additional questions are needed
### Why the one-round rule is needed

- More DM back-and-forth makes it easier to hit rate limits
- Two-party message loops are suppressed by **cascade detection** (sending is blocked when the maximum depth is exceeded within a configurable time window)
- Board posts are visible to other members and prevent duplication of information
### Exceptions

- Urgent blocker reports are not subject to the count limit
## Communication path rules

Message destinations follow the organizational structure:

| Situation | Destination | Example |
|------|------|-----|
| Reporting important progress or problems | Supervisor | `send_message(to="manager", content="タスクA完了", intent="report")` |
| Task instructions or delegation | Subordinate | `delegate_task(name="worker", instruction="レポート作成をお願い")` |
| Coordination with colleagues | Colleague (same supervisor) | `send_message(to="peer", content="レビューお願い", intent="question")` |
| Contacting other departments | Via own supervisor | `send_message(to="manager", content="開発部のXさんに確認してほしい件が...", intent="question")` |

- MUST: Do not contact members of other departments directly. Go through your own supervisor or the other party's supervisor
- MAY: You may communicate directly with colleagues (members who share the same supervisor)
## Blocker reporting (MUST)

If any of the following situations occurs during task execution, immediately report to the requester via `send_message`.
Do not leave the task in a "waiting" state.

- A file/directory is not found
- Access is denied due to insufficient permissions
- Prerequisites are not met
- Work was interrupted due to a technical issue
- Instructions are unclear and a decision cannot be made

Report to: Requester (send_message)
For major blockers (when a delay of 30 minutes or more is expected): Also notify a human via `call_human`
### Example of a blocker report

```
send_message(
    to="manager",
    content="""【ブロッカー報告】データ集計タスク

状況: 指定されたファイル /shared/data/sales_202601.csv が存在しません。
影響: 集計作業を開始できません。
必要なアクション: ファイルパスの確認、またはファイルの配置をお願いします。""",
    intent="report"
)
```

## Required elements of a request message (MUST)

When requesting a task from another Anima, always include the following five elements:

1. **Purpose** (why this work is needed)
2. **Target** (file path, resource)
3. **Expected outcome** (what constitutes completion)
4. **Deadline**
5. **Whether a completion report is required**

If these are missing, the recipient must reply to confirm, creating inefficient back-and-forth.