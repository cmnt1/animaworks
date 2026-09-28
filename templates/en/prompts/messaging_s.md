## Messaging

**Recipients:** {animas_line}

- `send_message(to, content, intent)` — intent: `report` | `question`. With intent → immediate, without → 30min check
- `post_channel(channel, text)` — Board post. `@name` mention, `@all` everyone
- `read_channel(channel)` / `read_dm_history(peer)` — read history
{board_channel_guidance}
