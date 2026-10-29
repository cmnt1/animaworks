## メッセージ送信

**送信可能な相手:** {animas_line}

DM送信:
```json
{{"name": "send_message", "arguments": {{"to": "相手名", "content": "メッセージ", "intent": "report"}}}}
```
- intent: `report` | `question`。Inbox は新しいメッセージのファイル変更通知で起動し、intent による起動フィルタはない

Board投稿:
```json
{{"name": "post_channel", "arguments": {{"channel": "general", "text": "投稿内容"}}}}
```
{board_channel_guidance}
- `read_channel(channel)` / `read_dm_history(peer)` で履歴参照
