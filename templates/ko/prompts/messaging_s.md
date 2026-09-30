## 메시지 전송

**전송 가능한 대상:** {animas_line}

- `send_message(to, content, intent)` — intent: `report` | `question`. Inbox 처리는 새 파일 변경 알림으로 시작하며 intent에 따른 시작 필터는 없다
- `post_channel(channel, text)` — Board 게시. `@名前` 멘션, `@all` 전체
- `read_channel(channel)` / `read_dm_history(peer)` — 기록 참조
{board_channel_guidance}
