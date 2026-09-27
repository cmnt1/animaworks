## メッセージ送信

**送信可能な相手:** {animas_line}

DM送信:
```json
{{"name": "send_message", "arguments": {{"to": "相手名", "content": "メッセージ", "intent": "report"}}}}
```
- intent: `report` | `question`。intentあり→即時処理、なし→30分巡回

Board投稿:
```json
{{"name": "post_channel", "arguments": {{"channel": "general", "text": "投稿内容"}}}}
```
{board_channel_guidance}
- `read_channel(channel)` / `read_dm_history(peer)` で履歴参照
