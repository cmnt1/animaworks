# Detailed Guide to Send Limits

Details of the multi-layer rate limiting used to prevent message storms (excessive message sending).
Refer to this when send errors occur or when you need to understand how the limits work.

## Implementation Locations

| Role | Module |
|------|------------|
| Destination resolution and external delivery to Slack/Chatwork | `core/messaging/outbound.py` (`resolve_recipient`, `send_external`) |
| Global budget and conversation depth (activity_log based) | `core/messaging/cascade_limiter.py` (`ConversationDepthLimiter`) |
| Internal DM delivery and logging | `core/messaging/messenger.py` (`Messenger.send`) |
| Per-run limits for `send_message` / `post_channel` and external routing entry point | `core/tooling/handler_comms.py` |
| Message-triggered heartbeat cooldown and cascade detection | `core/supervisor/inbox_rate_limiter.py` (`InboxRateLimiter`), `core/lifecycle/inbox_watcher.py` |
| Prompt injection of recent sends (behavioral awareness) | `core/memory/priming/outbound.py` (`collect_recent_outbound`) |

### `core/messaging/outbound.py` (Destination Resolution and External Delivery)

`send_message` resolves destinations from `handler_comms` using `resolve_recipient()`, delivering to internal Anima via `Messenger.send` or to Slack / Chatwork via `send_external()` for everything else. The set of known Anima is built from directory names in `~/.animaworks/animas/`.

**Resolution priority** (`resolve_recipient`):

1. **Exact match**: Known Anima name (case-sensitive) → internal
2. **User alias**: `external_messaging.user_aliases` in `config.json` (keys are case-insensitive) → first check whether `slack_user_id` / `chatwork_room_id` exist on the `preferred_channel` (slack / chatwork) side; if so, resolve externally on that channel. Otherwise, fall back to the other configured channel. Aliases with **neither contact available** → `RecipientNotFoundError` (message prompting configuration of `slack_user_id` or `chatwork_room_id`)
3. **`slack:USERID` prefix** (trim after the first 6 characters `slack:`, then uppercase) — **only when USERID is not empty**, resolve externally via Slack. When empty, do not resolve at this stage and proceed to the next stage
4. **`chatwork:ROOMID` prefix** (trim after the first 9 characters `chatwork:`) — **only when ROOMID is not empty**, resolve externally via Chatwork
5. **Raw Slack user ID**: regex `^U[A-Z0-9]{8,}$` (`re.IGNORECASE`) — leading `U` may be either case, followed by **8 or more** alphanumeric characters (at least 9 characters total) → Slack DM
6. **Case-insensitive match on Anima name** → internal (notation normalized to the official directory name)
7. If none of the above resolve, → `RecipientNotFoundError` (message including the list of known Anima and aliases. Empty-string destinations are rejected with a separate message)

**External sending** (`send_external`):

- Attempt order is `_build_channel_order`: first `ResolvedRecipient.channel`, then add untried channels if `slack_user_id` / `chatwork_room_id` exist.
- If an exception occurs on a channel, try the next one; if all fail, return `status: "error"`, `error_type: "DeliveryFailed"` as a JSON string.
- If no external channel can be assembled, → `NoChannelConfigured` (message indicating insufficient configuration of `external_messaging`).
- **Slack**: If `SLACK_BOT_TOKEN__{anima名}` (vault / shared) exists per Anima, post with the Bot token via `chat.postMessage`. Otherwise, prepend the prefix `[送信者名] ` to the body and post. Display name is `anima_name` (or `sender_name`), `icon_url` is `core.integrations._anima_icon_url.resolve_anima_icon_url` (`_resolve_outbound_icon` within `outbound`).
- **Chatwork**: Post with the per-Anima dedicated token `CHATWORK_API_TOKEN__<Anima名>` (resolved via identity; Anima without an assigned token cannot send). The body can similarly have the `[送信者名] ` prefix. Markdown is converted with `md_to_chatwork`.

## Unified Outbound Budget (DM + Board)

Count **`dm_sent` / `message_sent` / `channel_post`** on activity_log over the last 1 hour and 24 hours, and compare against the role's limit (or `status.json` override) (`cascade_limiter.check_global_outbound`).

- **Internal Anima DM**: Checked immediately before `Messenger.send`. On exceed, do not send and return error `Message`.
- **Board (`post_channel`)**: `handler_comms` runs the same `check_global_outbound` before posting.
- **DM to humans / external platforms** (via `send_external`): **The global budget is not checked immediately before the `send_external` call** (only per-run intent, destination count, and duplicate prevention apply). Meanwhile, `handler_comms` writes `message_sent` to activity_log on the external path **before `send_external`**. Therefore, even if the Slack / Chatwork API fails and returns a JSON error, the attempt may be **included in the 1-hour / 24-hour global count** if the log was written. Also, since the addition to `_replied_to` happens before delivery, **resends to the same `to` within the same session remain blocked**.

### Role-Based Defaults

Limits apply defaults based on `role` in `status.json` (`core.config.schemas.ROLE_OUTBOUND_DEFAULTS`). When unset, `general` equivalent applies.

| Role | Per hour | Per 24 hours | DM destinations per run |
|--------|-------------|--------------|---------------------|
| manager | 60 | 300 | 10 |
| engineer | 40 | 200 | 5 |
| writer | 30 | 150 | 3 |
| researcher | 30 | 150 | 3 |
| ops | 20 | 80 | 2 |
| general | 15 | 50 | 2 |

**Per-Anima override**: Can be overridden individually via `max_outbound_per_hour` / `max_outbound_per_day` / `max_recipients_per_run` in `status.json`. CLI:

```bash
animaworks anima set-outbound-limit <名前> --per-hour 40 --per-day 200 --per-run 5
animaworks anima set-outbound-limit <名前> --clear   # ロールデフォルトに戻す
```

## Layer 1: In-Session Guard (per-run)

Limits applied within a single session (heartbeat, conversation, task execution, etc.) (`handler_comms`).

| Limit | Description |
|------|------|
| DM intent | Only **`report` and `question`** intents are allowed for `send_message`. `intent=delegation` is deprecated and returns an error (task delegation goes through `delegate_task`). Any other intent is an error |
| Duplicate send prevention to same destination | DM to the same `to` string is allowed only once per session (determined by the `to` key for both internal and external) |
| DM destination count limit | Maximum N recipients per session (role / `status.json`). For N or more recipients, use Board |
| Board channel posting | `post_channel` to the same channel is allowed once per session (different channels are allowed) |

## Layer 2: Cross-Run Limits (Global Budget, Board Cooldown)

- **Global budget**: See "Unified Outbound Budget" above (enforced immediately before internal DM and Board sends. **External DMs have no global check before the API call**, but `handler_comms` leaves `message_sent` **before the API**, so they may be counted).
- **Board post cooldown**: `heartbeat.channel_post_cooldown_s` (default 300 seconds). Minimum interval between consecutive posts to the same channel. Determined by the last post time in the channel JSONL. **Independent of the global budget** (0 disables it).

**Excluded items**: Items in `Messenger.send` where `msg_type` is `ack` / `error` / `system_alert` are not subject to depth or global budget limits. `call_human` uses a separate path and is not subject to DM rate limits.

**Note**: Notification DMs from Board's `@メンション` to internal Anima (`board_mention`) go through `Messenger.send`, so they **can be subject to the global budget and depth checks**.

## Layer 3: Behavioral Awareness Priming

`collect_recent_outbound` formats the most recent `channel_post` / `message_sent` within the last 2 hours (up to 3 items) and injects them into the system prompt (`core/memory/priming/outbound.py`).

## Conversation Depth Limit (Two-Party DM)

When a two-party exchange exceeds `max_depth` within `depth_window_s`, `Messenger.send` addressed to an **internal Anima** is blocked (`check_depth`. See the `dm_sent`/`dm_received` in activity_log and its alias, `message_sent`/`message_received`).

| Configuration | Default value | Configuration key | Description |
|------|-------------|----------|------|
| Depth window | 600 seconds (10 minutes) | `heartbeat.depth_window_s` | Sliding window |
| Maximum depth | 6 turns | `heartbeat.max_depth` | 6 turns = 3 round trips expected. Sends are blocked if exceeded |

The displayed message is `messenger.depth_exceeded` in `core/i18n` (currently, the Japanese text is fixed as “6 turns in 10 minutes.” The actual threshold follows the configuration above).

If reading the log fails, the depth check is **fail-closed** (sending is blocked).

## Message-Triggered Heartbeat Suppression (Inbox)

To suppress spam from immediate heartbeats, `inbox_watcher` and `InboxRateLimiter` work together.

| Mechanism | Setting / Behavior |
|--------|----------------|
| **Intent filter** | `heartbeat.actionable_intents` (default `report`, `question`). Receives that do not match skip the message-triggered heartbeat (receives from humans / external platforms with an intent are handled separately) |
| **Cascade detection** | `heartbeat.cascade_window_s` (default 1800 seconds), `heartbeat.cascade_threshold` (default 3). When the threshold is exceeded, message-triggered heartbeats are suppressed (sending itself is not blocked) |
| **Message HB cooldown** | `heartbeat.msg_heartbeat_cooldown_s` (default 300 seconds). Prevents re-triggering too soon after the last message-triggered heartbeat ends |
| **Same-sender backlog** | If there are **5 or more** unprocessed messages from the same sender, defer the message-triggered heartbeat and leave it to the scheduled heartbeat |

## Configuration Summary

- **Role defaults / Per-Anima**: See the table above and `animaworks anima set-outbound-limit`
- **Depth, cascade, Board cooldown, and inbox behavior** (`heartbeat` in `config.json`):

```json
{
  "heartbeat": {
    "depth_window_s": 600,
    "max_depth": 6,
    "channel_post_cooldown_s": 300,
    "cascade_window_s": 1800,
    "cascade_threshold": 3,
    "msg_heartbeat_cooldown_s": 300,
    "actionable_intents": ["report", "question"]
  }
}
```

## When Limits Are Reached

### Error Messages (Examples)

- `GlobalOutboundLimitExceeded: 1時間あたりの送信上限（N通）に到達...` (when internal DM / Board is blocked)
- `GlobalOutboundLimitExceeded: 24時間あたりの送信上限（N通）に到達...`
- `GlobalOutboundLimitExceeded: アクティビティログ読み取り失敗のため送信をブロックしました` (on log failure, fail-closed)
- `ConversationDepthExceeded: ...` (depth exceeded. `messenger.depth_exceeded`)

### Resolution Steps

1. **For time-based limits**: Wait until the next 1-hour window. If not urgent, retry on the next heartbeat
2. **For 24-hour limits**: Narrow down to truly necessary messages. Record the content to send in `current_state.md` and send it in the next session
3. **For depth limits**: Wait until the window clears, or move complex discussions to Board
4. **Urgent contact**: `call_human` is not subject to DM rate limits. Contacting humans remains possible

### Best Practices for Reducing Send Volume

- Consolidate multiple report items into **a single message**
- Consolidate periodic reports into a single Board post (avoid distributing posts across multiple channels)
- Avoid short "acknowledged" replies; complete the exchange in one message that includes the next action
- Complete DM exchanges in a single round (see `communication/messaging-guide.md`)

## DM Log Archiving

DM history also remains in `shared/dm_logs/`, but the primary data source is **activity_log**.
`dm_logs` is archived on a 7-day rotation and is used only for fallback reads.
To review DM history, use the `read_dm_history` tool (it preferentially references activity_log internally).

## Avoiding Loops

- Before replying again to the other party's reply, consider whether it is truly necessary
- Confirmation / acknowledgment-only replies tend to cause loops
- Move complex discussions to a Board channel
