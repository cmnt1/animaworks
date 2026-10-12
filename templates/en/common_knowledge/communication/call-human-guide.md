# call_human Guide — Notifying Humans and Receiving Replies

## Overview

`call_human` is a tool for sending notifications to human administrators. Notifications always arrive in the Web UI chat screen and as toast notifications, and if a notification channel such as Slack is configured, they are also delivered there. **It is not one-way** — when a human replies in a Slack thread, that reply is automatically delivered to the originating Anima's Inbox.

## Sending

```
call_human(
    subject="件名",
    body="本文（状況・試したこと・依頼内容を含める）",
    priority="normal"  # "normal" | "high" | "urgent"
)
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `subject` | MUST | Subject (keep it concise) |
| `body` | MUST | Body (include situation, what was tried, and the request) |
| `priority` | MAY | `normal` (default), `high`, `urgent` |

### Use when:

- Issues with "high" urgency (risk of data loss, security, service shutdown)
- Decisions are needed that go beyond your own scope of judgment
- Escalation needed at the top-level Anima when there is no supervisor

See `troubleshooting/escalation-flowchart.md` for detailed decision criteria.

### Use when:

- `call_human` is a separate human notification path from `send_message`. Use it when urgent response is needed, as well as when a top-level Anima wants to briefly inform users of team results.

## Receiving Replies

### How it works

1. When a notification is sent via `call_human`, it arrives in the Web UI chat, and if Slack is configured, a message is also posted to Slack
2. A human replies in the **thread** of that message
3. The reply is automatically routed to the originating Anima's Inbox
4. The reply is processed in the next Inbox processing cycle (typically detected within 2 seconds)

### Characteristics of Reply Messages

Received reply messages have the following attributes:

- `source`: `"slack"` (reply via Slack)
- `from_person`: `"slack:U..."` format (Slack user ID)
- Processed the same way as regular Inbox messages

### When Waiting for a Reply

If you need to wait for a reply after sending `call_human`:

1. Record the waiting status in `state/current_state.md`
2. The reply will arrive automatically in the next Inbox processing
3. Even if there is no immediate reply, it will be delivered automatically once the human responds

### Responding to a Reply

Once you receive a reply, you can respond to it the same way as a regular Inbox message. However, since the reply target is a Slack user, respond with a chat response or a further `call_human` instead of `send_message`.

## Notes

- Reply routing is only supported for notifications sent in **Bot Token mode** (`chat.postMessage`). In Webhook mode, replies will not arrive (this is an administrator configuration issue, not something controlled by Anima)
- Reply mapping is retained for **7 days**. Replies to threads older than 7 days will not arrive
- Even if there is no reply from a human, you can follow up with another `call_human` as needed
