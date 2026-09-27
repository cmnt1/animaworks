---
name: discord-tool
description: >-
  Discord integration tool. Performs message send/receive, search, guild and channel listing, and reactions.
  Use when: Use when: you need to send messages on Discord, view channel lists, search within servers, react, or check threads.
tags: [communication, discord, external]
---
Understood. Please provide the Japanese content you’d like me to translate, and I’ll follow all your instructions precisely.# Discord Tool

An external tool for sending and receiving Discord messages, searching, listing servers/channels, and reacting.## How to Call

**Bash**: Run with `animaworks-tool discord <サブコマンド> [引数]`## Action List### guilds — Server List
```bash
animaworks-tool discord guilds
```
### channels — Channel List
```bash
animaworks-tool discord channels GUILD_ID
```
- `GUILD_ID`: Snowflake ID of the target guild (server) (required)### send — message sending
```bash
animaworks-tool discord send CHANNEL_ID MESSAGE [--reply-to MESSAGE_ID]
```
- `CHANNEL_ID`: Snowflake ID of the destination text channel
- `--reply-to`: Optional. ID of the message to reply to### Messages — Retrieving Messages
```bash
animaworks-tool discord messages CHANNEL_ID [-n 20]
```
### Search — Message Search
```bash
animaworks-tool discord search KEYWORD [-c CHANNEL_ID] [-n 50]
```
### react — Reactions (MCP only, CLI not supported)
- Add emoji reactions. **MCP only**. Not available in the CLI.## CLI Usage

```bash
animaworks-tool discord guilds
animaworks-tool discord channels GUILD_ID
animaworks-tool discord send CHANNEL_ID MESSAGE [--reply-to MESSAGE_ID]
animaworks-tool discord messages CHANNEL_ID [-n 20]
animaworks-tool discord search KEYWORD [-c CHANNEL_ID] [-n 50]
```
## Notes

- The Discord Bot Token must be pre-configured in credentials
- Channel IDs can be obtained by right-clicking in Discord's developer mode → "Copy ID"
- Messages have a 2000 character limit
- Guild ID, channel ID, and message ID are all numeric strings (Snowflake IDs)
- The bot requires the necessary permissions (Send Messages, Read Message History, Add Reactions, View Channels)