## Message Sending

**Who you can send to:** {animas_line}

- `send_message(to, content, intent)` — intent: `report` | `question`. Inbox starts with notifications of new file changes, with no intent-based startup filter
- `post_channel(channel, text)` — Board posts. `@名前` mentions, `@all` everyone
- `read_channel(channel)` / `read_dm_history(peer)` — history reference
{board_channel_guidance}
