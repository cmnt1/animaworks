## Messaging

**Recipients:** {animas_line}

DM:
```json
{{"name": "send_message", "arguments": {{"to": "recipient_name", "content": "message", "intent": "report"}}}}
```
- intent: `report` | `question`. A new Inbox message wakes processing via a file-change notification; intent does not filter wakeups

Board:
```json
{{"name": "post_channel", "arguments": {{"channel": "general", "text": "post content"}}}}
```
{board_channel_guidance}
- `read_channel(channel)` / `read_dm_history(peer)` for history
