<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/architecture/messaging.md -->
<!-- i18n: source-sha256=0975054575d95fdef233b9b53480548abb790dd9b8d8f084e1d3a0a4a55e18d4 generated=2026-09-27 engine=local model=deepseek-v4-flash translator=2 -->

> Confirmed commit: b304b7dc

# Messaging

Messages between Anima instances are delivered to their destinations via `send_message`. Arbitrary `intent` can be attached to messages, and the inbox dispatcher uses intents such as `delegation` along with the sender to determine whether immediate processing is needed. Conversation history is primarily read from activity logs, supplemented by DM history through shared configuration.

## Shared channels and company boundaries

`post_channel` posts to shared channels, and `read_channel` reads recent accessible posts. Channel metadata manages members, closed status, and company scope. An open channel with a specified company is limited to visibility from Anima instances within that company. The send paths for DMs and channels, as well as alias resolution for external destinations, are handled by `core/messaging/`.

## Send limits and receive dispatch

Three types of checks are used when sending. The number of recipients per single execution of `send_message` is limited to `max_recipients_per_run`. The number of sends between Anima instances is controlled by `max_outbound_per_hour` and a daily cap. Additionally, a depth limit is checked to prevent conversations from cycling rapidly between the same pair of Anima instances. Default values per role are in `core/config/schemas.py`, and Anima-specific overrides are in `status.json`. See the [configuration reference](../reference/config.md) for all settings.

On the receiving side, `core/supervisor/inbox_rate_limiter.py` checks cooldown, cascade detection, and received intents to adjust inbox lane startup. Therefore, send limit determination and suppression of receive processing initiation are implemented as separate responsibilities.

| role | 1 hour | 24 hours | Destinations per execution |
|---|---:|---:|---:|
| manager | 60 | 300 | 10 |
| engineer | 40 | 200 | 5 |
| writer / researcher | 30 | 150 | 3 |
| ops | 20 | 80 | 2 |
| general | 15 | 50 | 2 |

## Notifications to humans and external integrations

`call_human` is the path for sending notifications and confirmation requests to humans. There is a mode that requires a per-session confirmation key, which is confirmed using the key issued at runtime. See the [CLI reference](../reference/tool-cli.md) for CLI / tool usage.

External message sending supports configured Slack, Chatwork, and Discord destinations, while Zoom is used for meeting audio integration. See the [integration guide](../integrations/index.md) for channel configuration and individual integration procedures.
