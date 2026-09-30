## 메시지 전송

**전송 가능한 상대:** {animas_line}

DM 전송:
```json
{{"name": "send_message", "arguments": {{"to": "相手名", "content": "メッセージ", "intent": "report"}}}}
```
- intent: `report` | `question`. 새 Inbox 메시지는 파일 변경 알림으로 처리를 깨우며 intent에 따른 시작 필터는 없다

Board 게시:
```json
{{"name": "post_channel", "arguments": {{"channel": "general", "text": "投稿内容"}}}}
```
{board_channel_guidance}
- `read_channel(channel)` / `read_dm_history(peer)` 로 이력 참조
