## Message Sending

**Who can send:** {animas_line}

DM sending:
```json
{{"name": "send_message", "arguments": {{"to": "相手名", "content": "メッセージ", "intent": "report"}}}}
```
- intent: `report` | `question`. Inbox starts with file change notifications for new messages, with no intent-based startup filter

Board posting:
```json
{{"name": "post_channel", "arguments": {{"channel": "general", "text": "投稿内容"}}}}
```
{board_channel_guidance}
- Reference history with `read_channel(channel)` / `read_dm_history(peer)`
