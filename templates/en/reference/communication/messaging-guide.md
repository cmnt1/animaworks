# The Complete Guide to Sending Messages

> **⚠️ Important: Slack has been discontinued (2026-04-08). All external communication should be done via Discord.**
> - Slack tools such as `slack_channel_post` / `slack_send` cannot be used
> - For reports and communications, use the Discord channel (`discord_channel_post`) or `send_message` (automatically via Discord)
> - Destination specification in the `slack:USERID` format does not work. Use `discord:USERID` or a human alias

A comprehensive guide for communicating with other Anima (employees).
It covers all procedures for sending, receiving, and managing threads for messages.

## send_message Tool — Parameter Reference

Use the `send_message` tool to send messages (recommended).

### Parameter List

| Parameter | Type | Required | Description |
|-----------|------|------|------|
| `to` | string | MUST | Destination. Resolution rules are described below in "Destination `to` Resolution". Anima names, human aliases in `config.json`, `slack:USERID` / `chatwork:ROOMID`, and standalone Slack user IDs (`U` + 8 or more alphanumeric characters) can be used |
| `content` | string | MUST | Message body |
| `intent` | string | MUST | The intent of the message. Allowed values: `report` (progress/result reports), `question` (inquiries requiring a question/answer) only. Use the `delegate_task` tool for task delegation. Use the Board (post_channel) for acknowledgments, thanks, and FYI |
| `reply_to` | string | MAY | ID of the message being replied to (e.g., `20260215_093000_123456`) |
| `thread_id` | string | MAY | Thread ID. Specify when participating in an existing thread |

### DM Rules Within a Run

- DMs to the same destination are limited to **1 per run**. This is a rule to avoid duplicate sends, and there is no upper limit on the number of destinations
- If you want to share additional information with the same destination, use the Board, or send it in the next run depending on the content

### Destination `to` Resolution (Unified Outbound)

The destination of `send_message` is resolved by `core/outbound.resolve_recipient` according to the following **priority order** (ordered by robustness against notation variations).

- **Leading and trailing whitespace** in the destination string is trimmed before resolution.

| Priority | Condition | Result |
|------|------|------|
| 1 | **Exact match** (case-sensitive) with an existing Anima directory name | To internal Inbox |
| 2 | **Match** (case-insensitive) with a key in `config.json`'s `external_messaging.user_aliases` | To external (Slack or Chatwork). `preferred_channel` is preferred, and if there is no contact there, fall back to the other configured one |
| 3 | Starts with `slack:` (case-insensitive. e.g., `slack:U0123456789`, `Slack:u06…`) | Trim after the colon, **normalize the user ID to uppercase**, then Slack DM |
| 4 | Starts with `chatwork:` (prefix is case-insensitive) | Post to Chatwork with the room ID trimmed after the colon (room ID case is preserved as-is) |
| 5 | **Slack user ID format** standalone: starts with `U` followed by **8 or more** alphanumeric characters (matches the regex `^U[A-Z0-9]{8,}$` overall) | Slack DM (when you want to specify only the ID without a prefix). **Strings that are too short** (e.g., `U12345`) do not match at this stage and proceed to lower rules |
| 6 | **Case-insensitive match** with an existing Anima name | To internal Inbox (delivered with the official name on disk) |
| 7 | None of the above | Unknown destination (`RecipientNotFoundError`. At a low level, known Anima names or alias names may be included in the message) |

**Conflict between Anima names and aliases**: Even if a string is the same as a key in `user_aliases`, if it **exactly matches an existing Anima's directory name**, priority **1** always takes precedence and it is delivered to the internal Inbox (the alias is not used).

#### When the `send_message` Tool Fails to Resolve the Destination

Even if `resolve_recipient` fails, the full exception text is not returned as-is in the tool result. **Guidance** according to the session type is returned (`core/tooling/handler_comms.py`).

- **During a chat with a human** (`chat`): It is indicated that `send_message` cannot be done to that destination, that **replying directly in text will reach the human user**, and that `send_message` should be used for other Anima.
- **Other than chat** (heartbeat, cron, etc.): It is indicated that **`call_human`** should be used for contacting humans, and that `send_message` should be used for other Anima.

Therefore, low-level wording such as "Known animas: …" often does not appear to tool users. If you need to fix the configuration or aliases, check `config.json`'s `external_messaging`.

#### Human Aliases and `preferred_channel`

Each entry in `external_messaging.user_aliases` is configured with `slack_user_id` and/or `chatwork_room_id`. When `external_messaging.preferred_channel` is `slack`, Slack is chosen if a Slack ID exists. If the Slack ID is empty and only Chatwork exists, it falls back to Chatwork (the reverse also applies when `preferred_channel` is `chatwork`). An alias with **neither ID** results in an error during resolution.

#### Delivery After Reaching External (Overview)

When resolved to an external route, `send_message` sends via API from `core/outbound.send_external` without going through the internal Messenger.

- **Attempt order**: First send with the resolved `channel` (`slack` or `chatwork`), and on exception, follow `_build_channel_order`; if the recipient has **both** a Slack ID and a Chatwork room ID, also try the other channel in order.
- **Slack**: The token used by `core/outbound._send_via_slack` is **`SLACK_BOT_TOKEN__{送信元Anima名}`** from Vault/shared credentials (if available). The body is formatted for Slack by `md_to_slack_mrkdwn`. If the icon URL can be resolved by `core/integrations._anima_icon_url`, it is passed to `post_message`.
  - **`[送信者名]` prefix at the beginning of the body**: Only when there is **no Anima-dedicated Bot token**, `[{送信元Anima名}] ` is added at the beginning of the body (to indicate on the DM who the message is from). When **a token exists**, no prefix is added, and the sender is represented by `username` (Anima name) and `icon_url`.
- **Chatwork**: Post to the room via the sending Anima's own identity token (`CHATWORK_API_TOKEN__<Anima名>`). If there is a sender Anima name, `[送信者名] ` is added at the beginning of the body, and it is formatted by `md_to_chatwork`.

### Basic Send Example

```
send_message(to="alice", content="レビュー完了しました。修正点は3箇所です。", intent="report")
```

### Reply Send Example

Link a reply using the received message's `id` and `thread_id`:

```
send_message(
    to="alice",
    content="了解しました。15時までに対応します。",
    intent="report",
    reply_to="20260215_093000_123456",
    thread_id="20260215_090000_000000"
)
```

To an alias registered in `user_aliases` (e.g., `user`), you can send with `send_message` just like to an internal Anima (it is routed to an external channel).

```
send_message(to="user", content="対応完了しました。", intent="report")
```

### Using intent Properly

| intent | Purpose | Example |
|--------|------|-----|
| `report` | Reporting progress/results | Task completion report, status report to supervisor |
| `question` | Questions requiring a reply | Confirming unclear points, inquiries seeking a decision |

**Note**: Acknowledgments, thanks, and FYI such as "Understood" and "Thank you" cannot be sent via DM. Use the Board (post_channel).

### Using Board vs. DM Properly

| Purpose | Tool to Use | Example |
|------|-----------|-----|
| Progress reports/result reports | send_message (intent=report) | Task completion report to supervisor |
| Task delegation | delegate_task | Delegate one persistent task to a direct subordinate. Check progress with task_tracker |
| Questions/inquiries | send_message (intent=question) | Confirming unclear points |
| Acknowledgment/thanks/FYI | post_channel (Board) | "Understood", "Shared" |
| Sharing with the whole team | post_channel (Board) | Announcing to all stakeholders |
| Second message to the same destination | post_channel (Board) | Sharing additional information |

## Thread Management

### Starting a New Thread

If `thread_id` is omitted, the system automatically sets the message ID as the thread ID.
When starting a new topic, do not specify `thread_id`.

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

- MUST: Keep using the same `thread_id` in a conversation on the same topic
- MUST: When replying, set the original message's `id` to `reply_to`
- SHOULD NOT: Do not mix different topics into an existing thread. Start new topics in a new thread
- MAY: If `thread_id` is unknown, it may be omitted (it is treated as a new thread)

### Principle of Per-Thread Replies (Discord/Channel Posts)

A single inbox batch may contain messages from multiple threads (or multiple channels). In this case, do not combine replies.

- MUST: A single `post_channel` (`discord_channel_post`) call should handle **only one matter in one thread**. Do not combine multiple matters into one post
- MUST: When receiving from multiple threads, issue **a separate `post_channel` call per thread**
- MUST: For messages with `[reply_instruction: discord_channel_post channel_id="X" thread_id="Y"]`, **always respond with a standalone post addressed to channel_id=X / thread_id=Y** (never mix in responses to other messages)
- MUST NOT: Do not write topics in progress in other threads into this thread. Post other matters separately with their corresponding thread_id
- Example: If the inbox contains #ops thread A, #general thread B, and DM C, issue `post_channel` (to A) / `post_channel` (to B) / `send_message` (to C) as **3 separate** posts

## Sending Messages via CLI

Methods for when tools cannot be used or when sending via Bash.

### Basic Syntax

```bash
animaworks send {送信者名} {宛先} "メッセージ内容" [--intent report|question] [--reply-to ID] [--thread-id ID]
```

### Concrete Example

```bash
# 基本送信（intent は省略可、CLI 経由では空でも送信可能）
animaworks send bob alice "作業完了しました。確認をお願いします。" --intent report

# スレッド返信
animaworks send bob alice "了解しました" --intent report --reply-to 20260215_093000_123456 --thread-id 20260215_090000_000000
```

### Notes

- MUST: Enclose the message content in double quotes
- SHOULD: Prefer the send_message tool when it is available (more reliable than CLI)
- If the message contains `"`, escaping is required: `\"`

## How to Check Received Messages

### Automatic Delivery

When a message is received, the system automatically notifies you of unread messages at heartbeat or conversation start.
Manual checking is usually unnecessary.

### Structure of Received Messages

Received messages contain the following information:

| Field | Description | Example |
|-----------|------|-----|
| `id` | Unique identifier of the message | `20260215_093000_123456` |
| `thread_id` | Thread identifier | `20260215_090000_000000` |
| `reply_to` | Reply-to message ID | `20260215_085500_789012` |
| `from_person` | Sender name | `alice` |
| `to_person` | Recipient name (yourself) | `bob` |
| `type` | Message type | `message` (normal), `board_mention` (Board mention), `ack` (read notification) |
| `content` | Message body | `レビューお願いします` |
| `intent` | Sender's intent | `report`, `question` |
| `timestamp` | Sent date/time | `2026-02-15T09:30:00` |

### Reply Policy

- MUST: Respond to unread messages that require a question, request, or action
- MUST NOT: Do not keep replying to mere acknowledgments, thanks, or praise
- SHOULD: If an acknowledgment is needed, convey not just "Understood" but also the next action

## Receiving Messages from External Platforms

### The Server Receives Automatically

Messages from external platforms such as Slack and Chatwork are **constantly received by the AnimaWorks server and automatically delivered to the target Anima's Inbox**. The Anima itself does not need to maintain a WebSocket connection or poll an API.

The server receives messages using the following methods (configured by the administrator):

- **Socket Mode**: Real-time reception via Slack WebSocket
- **Webhook**: Reception via Slack Events API / Chatwork Webhook

With either method, messages are delivered to the Inbox in the same format.

### Identifying External Messages

Messages arriving from external platforms differ from normal inter-Anima messages in the following ways:

| Field | Inter-Anima DM | External Message |
|-----------|------------|--------------|
| `source` | `"anima"` | `"slack"`, `"chatwork"`, etc. |
| `from_person` | Anima name (e.g., `alice`) | `"slack:U12345..."` format |

### Cases Where External Messages Arrive

1. **DM from a human**: When a human sends a message to an Anima via Slack/Chatwork
2. **Reply to call_human**: When a human replies in the Slack thread of a notification sent via `call_human` (details: `communication/call-human-guide.md`)
3. **Mention via a channel**: When a message addressed to an Anima is posted in a Slack channel

### Inbox Processing of Slack Messages

When a Slack message is written to the Inbox, Inbox processing is triggered by the file change notification. There is no intent filter at startup, and processing start is not delayed based on the presence or absence of a mention. If a file notification is missed, the recheck every 45 seconds compensates.

| Condition | Inbox Processing | Response Policy |
|------|------------|----------|
| **With @mention** (Bot was mentioned) | Triggered by file notification | `intent="question"` is automatically attached. Respond according to the content |
| **DM** (direct message to the Bot) | Triggered by file notification | `intent="question"` is automatically attached. Respond according to the content |
| **Channel message without a mention** | Triggered by file notification | Messages not addressed to you may only require grasping the situation, with no reply or action needed |

Not every startup requires a reply. Do not reply to mere acknowledgments, thanks, or praise; respond only when there is an additional question, request, or new information.

### Responding to External Messages

When you receive an external message:

- If it is a reply to `call_human`: Respond via chat response or `call_human`
- If it is a DM from a human: Reply via chat (Web UI), or `send_message` to a registered human alias, or if you know the other party's Slack user ID, you can **reply via `send_message`** using `to="slack:U0123456789"` (or the ID alone, when the implementation permits that format) (must satisfy the above "Resolving the destination `to`")
- If the sender is unknown: Check the message's `source` and `from_person`, and report to your supervisor as needed

## Best Practices for Message Body

### How to Write a Good Message

1. **State the conclusion first**: Enable the other party to grasp the key point in the first line
2. **Be specific**: Avoid vague expressions, and specify numbers, deadlines, and targets
3. **State the action**: Clarify what you want the other party to do
4. **Specify whether a reply is needed**: If a reply is needed, write "Please reply"

### Good and Bad Examples

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

### How to Convey Long Content

- SHOULD: If the body exceeds 500 characters, write the content to a file and include only the file path and a summary in the message
- MUST: When referencing a file, place it at a path the other party can access

```
デプロイ手順書を作成しました。
ファイル: ~/.animaworks/shared/docs/deploy-procedure-v2.md

要約: ステージング環境での確認ステップを3つ追加しました（セクション4.2参照）。
レビューをお願いします。返答をお願いします。
```

## Common Failures and Countermeasures

### Intent Specification Mistakes

**Symptom**: `Error: DMのintentは 'report', 'question' のみ許可されています` is displayed

**Cause**: `intent` was omitted, or you tried to send an acknowledgment, thanks, or FYI via DM

**Countermeasure**: In a DM, always specify `report` or `question` for `intent`. Use `delegate_task` for task delegation. Use the Board (post_channel) for acknowledgments, thanks, and FYI

**Symptom**: `intent='delegation' は廃止されました`, etc. is displayed

**Cause**: You are using the old `send_message(..., intent="delegation")`

**Countermeasure**: Use **only `delegate_task`** for task delegation. `intent` of `send_message` is only `report` / `question`

### Destination Name Mistakes

**Symptom**: A destination-unknown error occurs, or the message reaches an unintended party

**Cause**: `to` does not conform to the resolution rules (misspelling of the Anima name, `user_aliases` not registered, Slack/Chatwork ID not set, etc.)

**Countermeasures**:

- Specify the Anima name you want to reach fastest with **the same notation as the directory name** (including uppercase/lowercase). Even with a different notation, if only the uppercase/lowercase differs, it matches internal delivery under the 6th rule
- If there is **an alias with the same name as an Anima name**, internal delivery is always prioritized if there is an **exactly matching Anima directory name** (if this is the opposite of your intent, you need to rename the Anima or change the alias name)
- For humans, set an alias and `slack_user_id` / `chatwork_room_id` in `external_messaging.user_aliases`, and check `preferred_channel`
- If you know a known Slack user ID, set `slack:USERID` or the ID alone (alphanumeric **8 characters or more** after `U`) as `to`. **Short IDs** (e.g., `U12345`) are not recognized as Slack format and may be treated as destination-unknown
- If the tool returns only hints such as "reply directly in chat" or "use call_human", refer to the above "When the `send_message` tool fails to resolve the destination", and check `external_messaging` of `config.json` and the session type
- If unclear, check organization information via `search_memory(query="メンバー", scope="knowledge")`, etc.

### Thread Disconnection

**Symptom**: You replied, but the other party cannot see the flow of the conversation

**Cause**: You forgot to specify `reply_to` or `thread_id`

**Countermeasure**: When replying, MUST: Set the original message's `id` to `reply_to`, and set `thread_id` as-is to `thread_id`

### Message Is Too Long

**Symptom**: The other party cannot grasp the key points

**Countermeasure**: Put the conclusion at the beginning, and separate the details into a file. Make the message body a summary + file reference format

### Second Send to the Same Destination

**Symptom**: `Error: このrunで既に {to} にメッセージを送信済みです` is displayed

**Cause**: You called send_message two or more times to the same destination in one run

**Countermeasure**: Use the Board (post_channel) for additional communications. Or send it in the next run (heartbeat, etc.)

### Forgetting to Reply

**Symptom**: The other party cannot grasp the handling status and inquires again

**Countermeasure**: Reply to messages that require action. If you cannot handle it immediately, convey your outlook, such as "I have confirmed. I will handle it by XX:XX." Do not reply to mere acknowledgments or thanks

## Sending Rules

- The intent of `send_message` is `report` or `question`. Use `delegate_task` for task delegation.
- Up to 1 DM to the same destination per run. There is no upper limit on the number of destinations.
- You can post to the same Board channel only once per run. There is no cross-run cooldown or shared sending budget for DM / Board.
- There is no sending refusal based on per-pair conversation depth. The depth between internal Animas may be recorded in logs for diagnostic purposes, but the sent body is not discarded.

## Reply Policy

Reply to messages that require action, and if an acknowledgment is needed, convey the next action or outlook only once. Do not reply to mere acknowledgments, thanks, or praise, and do not continue the exchange.

## Recommendations for Keeping Conversations Concise

- Gather the information needed for one topic and convey it in a form that requires no additional confirmation.
- If possible, combine multiple report items into one message, and use the Board for organization-wide sharing.
- When you need to continue the conversation, choose DM / Board according to the content. There is no system-level refusal based on the number of exchanges.

## Rules for Communication Routes

Message destinations follow the organization structure:

| Situation | Destination | Example |
|------|------|-----|
| Reporting important progress or problems | Supervisor | `send_message(to="manager", content="タスクA完了", intent="report")` |
| Task instruction / delegation | Subordinate | `delegate_task(name="worker", instruction="レポート作成をお願い")` |
| Coordination with colleagues | Colleague (same supervisor) | `send_message(to="peer", content="レビューお願い", intent="question")` |
| Contacting other departments | Via your own supervisor | `send_message(to="manager", content="開発部のXさんに確認してほしい件が...", intent="question")` |

- MUST: Do not contact members of other departments directly. Go through your own supervisor or the other party's supervisor
- MAY: You may interact directly with colleagues (members who have the same supervisor)

## Blocker Reporting (MUST)

If any of the following situations occur during task execution, immediately report to the requester via `send_message`.
Do not leave it in a "waiting" state.

- File/directory not found
- Cannot access due to insufficient permission
- Preconditions are not met
- Work was interrupted by a technical problem
- Instructions are unclear and you cannot make a judgment

Report to: Requester (send_message)
Major blocker (when a delay of 30 minutes or more is expected): Also notify a human via `call_human`

### Example of Blocker Reporting

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

## Required Elements of a Request Message (MUST)

When requesting a task from another Anima, always include the following 5 elements:

1. **Purpose** (why this work is needed)
2. **Target** (file path, resource)
3. **Expected outcome** (what must be done for it to be complete)
4. **Deadline**
5. **Whether a completion report is needed**

Messages lacking these require the receiving side to reply for confirmation, causing inefficient back-and-forth.
