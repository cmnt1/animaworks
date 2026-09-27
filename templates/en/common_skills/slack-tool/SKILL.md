---
name: slack-tool
description: >-
  Slack integration tool. It handles message sending and receiving, search, checking unreplied messages, channel list, and emoji reactions.
  Use when: Use when: you need to post to Slack, view the channel list, reply in threads, check unreplied messages, or add reactions.
tags: [communication, slack, external]
---
Understood. Please provide the Japanese content you’d like me to translate, and I’ll follow all the specified rules.# Slack Tools

External tools for sending, receiving, and searching Slack messages and reactions.## How to Invoke

**Bash**: Run with `animaworks-tool slack <サブコマンド> [引数]`## Action List### send — Send Message
```bash
animaworks-tool slack send CHANNEL MESSAGE [--thread TS]
```
### messages — Retrieving Messages
```bash
animaworks-tool slack messages CHANNEL [-n 20]
```
### Search — Message Search
```bash
animaworks-tool slack search KEYWORD [-c CHANNEL] [-n 50]
```
### unreplied — Check Unreplied Messages
```bash
animaworks-tool slack unreplied [--json]
```
### channels — Channel List
```bash
animaworks-tool slack channels
```
### react — Emoji reactions
- `emoji`: Slack emoji name (without colons. e.g., `thumbsup`, `eyes`, `white_check_mark`)
- `message_ts`: Timestamp of the message being reacted to (can be obtained from the result of the `messages` action)
- **Note**: The `react` action is not supported in the CLI. Use it via MCP.## CLI Usage

```bash
animaworks-tool slack send CHANNEL MESSAGE [--thread TS]
animaworks-tool slack messages CHANNEL [-n 20]
animaworks-tool slack search KEYWORD [-c CHANNEL] [-n 50]
animaworks-tool slack unreplied [--json]
animaworks-tool slack channels
```
## Notes

- The Slack Bot Token must be pre-configured in credentials
- Specify the channel by name with # or by channel ID
- The `reactions:write` scope is required for reactions