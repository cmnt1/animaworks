<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/architecture/messaging.md -->
<!-- i18n: source-sha256=ac6c7cb1c61d3539dbeae4d6d8eec7a67e5de52f8b453a9bd000e6bd535b37b5 generated=2026-09-30 engine=local model=deepseek-v4-flash translator=2 -->

> Confirmed commit: b304b7dc

# Messaging

Messages between Anima instances are delivered to their destination via `send_message`. `intent` is metadata indicating the purpose of a message and is not used to filter Inbox startup. Conversation history is read primarily from activity logs, supplemented by DM history depending on shared configuration.

## Shared channels and company boundaries

`post_channel` posts to shared channels, and `read_channel` reads recent accessible posts. Channel metadata manages members, closed status, and company scope. An open channel with a specified company is limited to visibility from Anima instances within that company. The send paths for DMs and channels, as well as alias resolution for external destinations, are handled by `core/messaging/`.

## Send Rules and Receive Dispatch

`send_message` uses `report` / `question` intents and rejects a second message to the same destination within the same run. There is no limit on the number of destinations. `post_channel` can post to the same channel at most once per run, but there is no cooldown between runs. There is no time- or day-based send budget, nor send rejection based on conversation depth. `Messenger.send` records messages in the activity log, and even when depth is recorded in diagnostic logs, delivery is not rejected.

On the receiving side, `core/supervisor/inbox_rate_limiter.py` monitors file change notifications for the Inbox JSON and starts the Inbox lane if there are unread messages. Concurrency is limited to one; messages arriving during execution are batched into the next single run. To guard against missed notifications, it re-checks every 45 seconds, and on Provider errors it retains unread messages while waiting for `rate_guard`'s recovery time. `overflow_inbox` remains as capacity protection.

## Notifications to humans and external integrations

`call_human` is the path for sending notifications and confirmation requests to humans. There is a mode that requires a per-session confirmation key, which is confirmed using the key issued at runtime. See the [CLI reference](../reference/tool-cli.md) for CLI / tool usage.

External message sending supports configured Slack, Chatwork, and Discord destinations, while Zoom is used for meeting audio integration. See the [integration guide](../integrations/index.md) for channel configuration and individual integration procedures.
