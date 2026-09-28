## Message Sending

**Who can send to:** {animas_line}

- `send_message(to, content, intent)` — intent: `report` | `question`. With intent → immediate processing, without → 30-minute patrol
- `post_channel(channel, text)` — Board post. `@名前` mention, `@all` everyone
- `read_channel(channel)` / `read_dm_history(peer)` — history reference
{board_channel_guidance}
