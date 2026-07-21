# Detailed Guide to Sending Limits

Multi-layer rate limiting that prevents excessive outbound traffic (message storms).
Refer to this when send errors occur or when you need to understand how the limits work.

## Where It Is Implemented

| Role | Module |
|------|--------|
| Recipient resolution and external delivery to Slack/Chatwork | `core/outbound.py` (`resolve_recipient`, `send_external`) |
| Global budget and conversation depth (activity_log–based) | `core/cascade_limiter.py` (`ConversationDepthLimiter`) |
| Internal DM delivery and logging | `core/messenger.py` (`Messenger.send`) |
| `send_message` / `post_channel` per-run limits and external routing entry | `core/tooling/handler_comms.py` |
| Message-triggered heartbeat cooldown and cascade detection | `core/supervisor/inbox_rate_limiter.py` (`InboxRateLimiter`), `core/lifecycle/inbox_watcher.py` |
| Recent-send priming (behavior awareness) | `core/memory/priming/outbound.py` (`collect_recent_outbound`) |

### `core/outbound.py` (recipient resolution and external delivery)

`send_message` resolves the recipient via `resolve_recipient()` from `handler_comms`: internal Anima → `Messenger.send`; otherwise → `send_external()` to Slack / Chatwork. The set of known Anima names is built from directory names under `~/.animaworks/animas/`.

**Resolution order** (`resolve_recipient`):

1. **Exact match**: Known Anima name (case-sensitive) → internal
2. **User alias**: `external_messaging.user_aliases` in `config.json` (keys are case-insensitive) → check `preferred_channel` (slack / chatwork) for `slack_user_id` / `chatwork_room_id`; if present, resolve externally on that channel. Otherwise fall back to the other configured channel when available. An alias with **no contact on either channel** raises `RecipientNotFoundError` (message prompts configuring `slack_user_id` or `chatwork_room_id`)
3. **`slack:USERID` prefix** (trim after the first 6 characters `slack:`, then normalize case)—Slack external resolution **only when USERID is non-empty**. If empty, this step does not resolve; evaluation continues to later steps
4. **`chatwork:ROOMID` prefix** (trim after the first 9 characters `chatwork:`)—Chatwork external resolution **only when ROOMID is non-empty**
5. **Bare Slack user ID**: Regex `^U[A-Z0-9]{8,}$` with `re.IGNORECASE`—leading `U` may be upper or lower case, followed by **8 or more** alphanumeric characters (at least 9 characters total) → Slack DM
6. **Case-insensitive Anima name match** → internal (normalized to the canonical directory name)
7. If none of the above apply → `RecipientNotFoundError` (message includes known Anima and alias lists). Empty-string recipients are rejected with a separate message

**External send** (`send_external`):

- Attempt order follows `_build_channel_order`: first `ResolvedRecipient.channel`, then append any not-yet-tried channel that has `slack_user_id` / `chatwork_room_id`.
- If a channel raises an exception, the next channel is tried; if all fail, a JSON string is returned with `status: "error"` and `error_type: "DeliveryFailed"`.
- If no external channel can be assembled, `NoChannelConfigured` is raised (message indicates insufficient `external_messaging` configuration).
- **Slack**: If the per-Anima `SLACK_BOT_TOKEN__{anima_name}` (vault / shared) exists, post with the bot token via `chat.postMessage`. Otherwise prefix the body with `[SenderName] `. Display name is `anima_name` (or `sender_name`); `icon_url` comes from `core.tools._anima_icon_url.resolve_anima_icon_url` (`_resolve_outbound_icon` inside `outbound`).
- **Chatwork**: Post using the per-Anima token `CHATWORK_API_TOKEN__<anima_name>` (via identity resolution; Animas without an assigned token cannot post). Body may similarly use a `[SenderName] ` prefix. Markdown is converted with `md_to_chatwork`.

## Unified Outbound Budget (DM + Board)

Counts **`dm_sent` / `message_sent` / `channel_post`** in activity_log over the last hour and 24 hours and compares them to caps from the role (or `status.json` overrides) (`cascade_limiter.check_global_outbound`).

- **DM to internal Anima**: Checked immediately before `Messenger.send`. On exceed, no send; an error `Message` is returned.
- **Board (`post_channel`)**: `handler_comms` runs the same `check_global_outbound` before posting.
- **DM to humans / external platforms** (via `send_external`): **The global budget is not checked immediately before `send_external`** (only per-run intent, recipient count, and duplicate prevention). However, `handler_comms` writes `message_sent` to activity_log **before** `send_external` on the external path. Therefore, even if the Slack / Chatwork API fails and JSON error is returned, **the attempt may still count** toward the 1-hour / 24-hour global totals if the log entry was written. Also, `_replied_to` is updated before delivery, so **a resend to the same `to` in the same session remains blocked**.

### Role-Based Defaults

Limits use defaults for `status.json` `role` (`core.config.schemas.ROLE_OUTBOUND_DEFAULTS`). If unset, behavior matches `general`.

| Role | Per hour | Per 24h | DM recipients per run |
|------|----------|---------|------------------------|
| manager | 60 | 300 | 10 |
| engineer | 40 | 200 | 5 |
| writer | 30 | 150 | 3 |
| researcher | 30 | 150 | 3 |
| ops | 20 | 80 | 2 |
| general | 15 | 50 | 2 |

**Per-Anima override**: `max_outbound_per_hour` / `max_outbound_per_day` / `max_recipients_per_run` in `status.json`. CLI:

```bash
animaworks anima set-outbound-limit <name> --per-hour 40 --per-day 200 --per-run 5
animaworks anima set-outbound-limit <name> --clear   # Revert to role defaults
```

## Layer 1: Session Guard (per-run)

Limits within one session (heartbeat, chat, task execution, etc.) (`handler_comms`).

| Limit | Description |
|-------|-------------|
| DM intent | `send_message` allows only **`report` and `question`**. `intent=delegation` is treated as deprecated and errors (use `delegate_task` for delegation). Any other intent errors |
| No resend to same recipient | At most one DM per session to the same `to` string (internal and external; keyed by `to`) |
| DM recipient cap | At most N recipients per session (role / `status.json`). For N+ recipients, use Board |
| Board channel posts | At most one `post_channel` per channel per session (other channels allowed) |

## Layer 2: Cross-Run Limits (Global Budget and Board Cooldown)

- **Global budget**: See “Unified Outbound Budget” above (enforced immediately before internal DM and Board sends. **External DM has no global check before the API call**, but because `handler_comms` may write **`message_sent` before the API**, the attempt can still count toward the budget).
- **Board post cooldown**: `heartbeat.channel_post_cooldown_s` (default 300 seconds). Minimum gap between consecutive posts to the same channel, using last post time in the channel JSONL. **Independent of the global budget** (set to 0 to disable).

**Excluded**: In `Messenger.send`, messages with `msg_type` `ack` / `error` / `system_alert` skip depth and global budget. `call_human` uses a separate path and is outside DM rate limits.

**Note**: Notification DMs to internal Anima from Board `@mentions` (`board_mention`) go through `Messenger.send`, so they **can** be subject to the global budget and depth checks.

## Layer 3: Behavior-Aware Priming

`collect_recent_outbound` formats up to three `channel_post` / `message_sent` events within the last 2 hours and injects them into the system prompt (`core/memory/priming/outbound.py`).

## Conversation Depth Limit (Two-Party DM)

When exchanges between two parties exceed `max_depth` within `depth_window_s`, **`Messenger.send` to internal Anima** is blocked (`check_depth`, using activity_log `dm_sent`/`dm_received` and aliases `message_sent`/`message_received`).

| Setting | Default | Config Key | Description |
|---------|---------|------------|-------------|
| Depth window | 600s (10 min) | `heartbeat.depth_window_s` | Sliding window |
| Max depth | 6 turns | `heartbeat.max_depth` | 6 turns ≈ 3 round-trips; send blocked above this |

User-facing text comes from `core/i18n` `messenger.depth_exceeded` (Japanese currently uses a fixed “6 turns in 10 minutes” string; actual thresholds follow the settings above).

If activity log reads fail, depth check is **fail-closed** (send blocked).

## Suppressing Message-Triggered Heartbeat (Inbox)

`inbox_watcher` and `InboxRateLimiter` work together to reduce spam from immediate heartbeats.

| Mechanism | Setting / behavior |
|-----------|-------------------|
| **Intent filter** | `heartbeat.actionable_intents` (default `report`, `question`). Receipts that do not match skip message-triggered heartbeat (human / external platform traffic with intent is handled separately) |
| **Cascade detection** | `heartbeat.cascade_window_s` (default 1800s), `heartbeat.cascade_threshold` (default 3). Above threshold, message-triggered heartbeat is suppressed (sending itself is not blocked) |
| **Message HB cooldown** | `heartbeat.msg_heartbeat_cooldown_s` (default 300s). Suppresses retriggers too soon after the last message-triggered heartbeat ended |
| **Same-sender backlog** | If **5 or more** unprocessed messages from the same sender exist, defer message-triggered heartbeat to the scheduled heartbeat |

## Configuration Summary

- **Role defaults / Per-Anima**: Tables above and `animaworks anima set-outbound-limit`
- **Depth, cascade, Board cooldown, inbox behavior** (`heartbeat` in `config.json`):

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

## When Limits Are Hit

### Example Error Messages

- `GlobalOutboundLimitExceeded: ...` — per-hour send limit (N messages) reached (when internal DM / Board is blocked)
- `GlobalOutboundLimitExceeded: ...` — per-24h send limit (N messages) reached
- `GlobalOutboundLimitExceeded: Sending blocked because the activity log could not be read` (log read failure, fail-closed)
- `ConversationDepthExceeded: ...` — depth exceeded (`messenger.depth_exceeded` in `core/i18n`; exact wording follows locale and may not reflect custom `heartbeat` thresholds)

### What to Do

1. **Hour limit**: Wait for the next hour window. If not urgent, retry on the next heartbeat
2. **24-hour limit**: Keep only truly necessary sends. Record content in `current_state.md` and send in a later session
3. **Depth limit**: Wait until the window clears or move complex discussion to Board
4. **Urgent contact**: `call_human` is outside DM rate limits; human notification remains available

### Best Practices for Conserving Send Volume

- Combine multiple report items into **one message**
- Put routine reports in a **single Board post** (avoid scattering across channels)
- Avoid bare “OK” replies; finish in one message with the next action when possible
- Complete DM exchanges in one round (see `communication/messaging-guide.md`)

## DM Log Archive

DM history also lives under `shared/dm_logs/`, but the **primary source is activity_log**.
`dm_logs` rotates every 7 days and is used only for fallback reads.
Use the `read_dm_history` tool to inspect DM history (it prefers activity_log internally).

## Avoiding Loops

- Before replying again to a peer, consider whether it is really needed
- Acknowledgment-only replies often cause loops
- Move complex discussions to Board channels
