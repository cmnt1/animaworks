# Message Send and Receive Operations Guide

This document summarizes the operations for message delivery, Inbox startup, and avoiding conversation loops. The previous send budget, depth rejection, Inbox cooldown / cascade / intent filters have been removed.

## Remaining Rules for Sending

- The intent of `send_message` is `report` or `question`. Use `delegate_task` for task delegation.
- Only one DM to the same recipient per run. This is a guard to avoid duplicate sends; there is no limit on the number of recipients.
- Only one `post_channel` to the same Board channel per run. You can post to the same channel again in a different run.
- There is no hourly or daily send budget, and no send rejection based on conversation depth between pairs.
- Conversation depth between internal Anima instances may be logged for diagnostic purposes. This is observation only; it does not discard message content or reject sending.

## Responses to Acknowledgments, Thanks, and Praise

If the received content is only an acknowledgment, thanks, or praise, do not reply. Do not continue the exchange; only take necessary action if there are additional questions, requests, or new information.
For a work request, send an acknowledgment once, if needed, along with the outlook and next steps.

## Inbox Startup and Processing

Detect new JSON files in the Inbox via file change notifications, and start Inbox processing if there are unread messages.
Only one Inbox processing run can be active at a time. Messages that arrive during execution are processed together in the next run.
To guard against missed file notifications, re-check for unread messages every 45 seconds. On provider-side failures, wait for the recovery time of `rate_guard` and keep unread messages.

If there are a large number of messages, offloading to `state/overflow_inbox/` remains as capacity protection. This is not a suppression based on sender or intent; offloaded messages can be reviewed and processed later.

## Logging and Verification

`Messenger.send` records sent messages in the activity log. If conversations continue over a short period, diagnostic logs may be added, but the send result is unchanged.
The most recent `message_sent` / `channel_post` are used by `core/memory/priming/outbound.py` for priming.

If a message cannot be sent, check the actual delivery errors for destination resolution, permissions, and external channels. There is no need to wait for rate limits or conversation depth limits.

## Implementation Location

| Role | Module |
|------|------------|
| Destination resolution and external delivery to Slack / Chatwork | `core/messaging/outbound.py` |
| Internal DM delivery, activity log recording, and depth diagnostic logging | `core/messaging/messenger.py` |
| DM duplicate prevention and Board duplicate prevention within a run | `core/tooling/handler_comms.py` |
| Inbox file wake, single execution, and provider backoff | `core/supervisor/inbox_rate_limiter.py` |
| Inbox capacity protection overflow | `core/anima/inbox_overflow.py` |
| Prompt injection of recent sends | `core/memory/priming/outbound.py` |
