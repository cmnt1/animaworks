## Messaging

**Recipients:** {animas_line}

DM:
```json
{{"name": "send_message", "arguments": {{"to": "recipient_name", "content": "message", "intent": "report"}}}}
```
- intent: `report` | `question`. With intent → immediate, without → 30min check

Board:
```json
{{"name": "post_channel", "arguments": {{"channel": "general", "text": "post content"}}}}
```
{board_channel_guidance}
- `read_channel(channel)` / `read_dm_history(peer)` for history
