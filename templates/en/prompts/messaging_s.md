## Messaging

**Recipients:** {animas_line}

- `send_message(to, content, intent)` — intent: `report` | `question`. Inbox processing wakes on new-file notifications; intent does not filter wakeups
- `post_channel(channel, text)` — Board post. `@name` mention, `@all` everyone
- `read_channel(channel)` / `read_dm_history(peer)` — read history
{board_channel_guidance}
