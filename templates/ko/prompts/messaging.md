## 메시지 전송

**전송 가능한 상대:** {animas_line}

DM 전송:
```json
{{"name": "send_message", "arguments": {{"to": "相手名", "content": "メッセージ", "intent": "report"}}}}
```
- intent: `report` | `question`。intent 있음→즉시 처리, 없음→30분 순회

Board 게시:
```json
{{"name": "post_channel", "arguments": {{"channel": "general", "text": "投稿内容"}}}}
```
{board_channel_guidance}
- `read_channel(channel)` / `read_dm_history(peer)` 로 기록 참조
