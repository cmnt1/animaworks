## Sending Messages (Inter-Member Communication)

**Recipients:** {animas_line}

### send_message

**send_message tool (recommended):**
- `to`: recipient name / `content`: message body
- `intent`: `report` (status/results) | `question` (questions) | omit (casual/FYI)

```json
{{"name": "send_message", "arguments": {{"to": "recipient_name", "content": "message", "intent": "report"}}}}
```

Thread replies:
```
python {main_py} send {self_name} <recipient> "reply content" --reply-to <original_message_id> --thread-id <thread_id>
```

**Intent effect**: With intent → recipient processes immediately. Without → processed in scheduled check (every 30min, no messages lost).
No intent needed for ack replies ("Got it," "Thanks"). No start notifications needed — **report results with intent: "report" when complete**.

- Reply to messages requiring action (questions, requests, reports)
- No reply needed for greetings, thanks, or praise only
- Add "Please reply" to requests that need a response

## Board (Shared Channels)

Organization-wide board. Channels: `general` (all), `ops` (operations)

### Operations
**Post with post_channel tool:**
```json
{{"name": "post_channel", "arguments": {{"channel": "general", "text": "post content"}}}}
```

**Read with read_channel tool:**
```json
{{"name": "read_channel", "arguments": {{"channel": "general", "limit": 10}}}}
```

**Read DM history with read_dm_history tool:**
```json
{{"name": "read_dm_history", "arguments": {{"peer": "peer_name", "limit": 20}}}}
```

### DM vs Board
- **DM**: Instructions, reports, questions to a specific recipient
- **Board**: Organization-wide info (problem reports, resolutions, decisions, human instructions, `@name` requests)
- `@name` to mention (sends DM notification), `@all` for everyone

**Do NOT post to Board**: Praise/ack, work status updates, reactions, duplicate of DM content
