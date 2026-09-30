<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/architecture/messaging.md -->
<!-- i18n: source-sha256=0975054575d95fdef233b9b53480548abb790dd9b8d8f084e1d3a0a4a55e18d4 generated=2026-09-30 engine=local model=deepseek-v4-flash translator=2 -->

> Confirmed commit: b304b7dc

# Messaging

Messages between Anima instances are delivered to their destinations via `send_message`. `intent` is metadata describing a message's purpose; it is not used to filter Inbox wakeups. Conversation history is primarily read from activity logs, supplemented by DM history through shared configuration.

## Shared channels and company boundaries

`post_channel` posts to shared channels, and `read_channel` reads recent accessible posts. Channel metadata manages members, closed status, and company scope. An open channel with a specified company is limited to visibility from Anima instances within that company. The send paths for DMs and channels, as well as alias resolution for external destinations, are handled by `core/messaging/`.

## Sending rules and receive dispatch

`send_message` uses the `report` / `question` intents and rejects a second DM to the same recipient in one run. There is no recipient-count cap. `post_channel` may post once to a given channel per run, with no cross-run cooldown. There are no hourly/daily send budgets or conversation-depth send blocks. `Messenger.send` records messages in the activity log and may log depth for diagnostics without rejecting delivery.

On the receiving side, `core/supervisor/inbox_rate_limiter.py` watches for Inbox JSON file changes and starts the Inbox lane when messages are unread. Only one job runs at a time; arrivals during a run are combined into the next run. A 45-second safety rescan catches missed notifications, and provider failures wait for `rate_guard` recovery while retaining unread messages. `overflow_inbox` remains as capacity protection.

## Notifications to humans and external integrations

`call_human` is the path for sending notifications and confirmation requests to humans. There is a mode that requires a per-session confirmation key, which is confirmed using the key issued at runtime. See the [CLI reference](../reference/tool-cli.md) for CLI / tool usage.

External message sending supports configured Slack, Chatwork, and Discord destinations, while Zoom is used for meeting audio integration. See the [integration guide](../integrations/index.md) for channel configuration and individual integration procedures.
