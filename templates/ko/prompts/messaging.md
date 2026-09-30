## 메시지 전송

**전송 가능한 대상:** {animas_line}

DM 전송:
```json
{{"name": "send_message", "arguments": {{"to": "相手名", "content": "メッセージ", "intent": "report"}}}}
```
- intent: `report` | `question`. Inbox는 새 메시지의 파일 변경 알림으로 시작되며, intent에 의한 시작 필터는 없음

Board 게시:
```json
{{"name": "post_channel", "arguments": {{"channel": "general", "text": "投稿内容"}}}}
```
{board_channel_guidance}
- `read_channel(channel)` / `read_dm_history(peer)`로 기록 열람
