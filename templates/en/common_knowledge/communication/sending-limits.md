# Messaging and Inbox Operations

This guide describes message delivery, Inbox triggering, and loop-avoidance behavior.
The former global send budgets, depth-based send rejection, and Inbox cooldown / cascade / intent filters have been removed.

## Remaining send rules

- `send_message` requires the `report` or `question` intent. Use `delegate_task` for task delegation.
- A run may send at most one DM to the same recipient. This prevents duplicate messages; there is no recipient-count cap.
- A run may post once to a given Board channel with `post_channel`. The same channel may be used again in a later run.
- There are no hourly/daily send budgets or pairwise conversation-depth send blocks.
- Conversation depth between internal Animas may be logged for diagnostics. This is observation only: it never rejects a send or discards the message body.

## Responding to acknowledgements and thanks

Do not reply when an incoming message is only an acknowledgement, thanks, or praise. Do not continue the exchange; act only when there is an additional question, request, or new information.
When acknowledging a work request is useful, do it once and include the next action or expected timing.

## Inbox triggering and processing

A filesystem notification for a new Inbox JSON file wakes the Inbox watcher, which starts processing when messages are unread.
Only one Inbox job runs at a time. Messages that arrive while it runs are combined into the next run.
A 45-second safety rescan catches missed filesystem notifications. Provider failures wait for `rate_guard` recovery while leaving unread messages in place.

When message volume is high, `state/overflow_inbox/` remains as capacity protection. It does not suppress messages by sender or intent; overflowed messages can be reviewed and processed later.

## Recording and troubleshooting

`Messenger.send` records sent messages in the activity log. A short burst in an internal Anima conversation may produce an additional diagnostic depth log, but delivery is unaffected.
Recent `message_sent` / `channel_post` events are used by `core/memory/priming/outbound.py` for priming.

If a message is not delivered, check recipient resolution, permissions, and the actual external-channel delivery error. There is no rate-budget or conversation-depth window to wait out.

## Implementation locations

| Responsibility | Module |
|------|------------|
| Destination resolution and Slack / Chatwork delivery | `core/messaging/outbound.py` |
| Internal DM delivery, activity logging, and diagnostic depth logging | `core/messaging/messenger.py` |
| Duplicate DM prevention and per-run Board channel guard | `core/tooling/handler_comms.py` |
| Inbox file wakeups, single-run coordination, and provider backoff | `core/supervisor/inbox_rate_limiter.py` |
| Inbox capacity protection via overflow files | `core/anima/inbox_overflow.py` |
| Prompt injection of recent sends | `core/memory/priming/outbound.py` |
