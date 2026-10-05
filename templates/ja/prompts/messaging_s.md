## メッセージ送信

**送信可能な相手:** {animas_line}

- `send_message(to, content, intent)` — intent: `report` | `question`。Inbox は新規ファイルの変更通知で起動し、intent による起動フィルタはない
- `post_channel(channel, text)` — Board投稿。`@名前`メンション、`@all`全員
- `read_channel(channel)` / `read_dm_history(peer)` — 履歴参照
{board_channel_guidance}
