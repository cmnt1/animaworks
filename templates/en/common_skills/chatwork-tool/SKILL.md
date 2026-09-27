---
name: chatwork-tool
description: >-
  Chatwork integration tool. Performs message send/receive, search, unread reply check, and room listing.
  Use when: Use when: you need to send messages, retrieve room lists, check unread replies, search chats, or handle mentions in Chatwork.
tags: [communication, chatwork, external]
---
Understood. Please provide the Japanese content you’d like me to translate, and I’ll follow all the specified rules.# Chatwork Tool

An external tool for sending, receiving, searching, and managing Chatwork messages.## How to Call

**Bash**: Run with `animaworks-tool chatwork <サブコマンド> [引数]`. See below for syntax.## Action List### send — Send Message
```bash
animaworks-tool chatwork send ROOM MESSAGE
```
### Messages — Retrieving Messages
```bash
animaworks-tool chatwork messages ROOM [-n 20]
```
### Search — Message Search
```bash
animaworks-tool chatwork search KEYWORD [-r ROOM] [-n 50]
```
### unreplied — Check Unreplied Messages
```bash
animaworks-tool chatwork unreplied [--json]
```
- `include_toall` (optional, default: false): Whether to include messages addressed to everyone

Use when: checking for messages that have not yet been replied to.### rooms — Room List
```bash
animaworks-tool chatwork rooms
```
### mentions — Fetching Mentions
```bash
animaworks-tool chatwork mentions [--json]
```
- `include_toall` (optional, default: false): Whether to include messages addressed to everyone

Use when:### delete — Delete messages (own messages only)
```bash
animaworks-tool chatwork delete ROOM MESSAGE_ID
```
### sync — Message synchronization (cache update)
```bash
animaworks-tool chatwork sync [ROOM]
```
## CLI Usage

```bash
animaworks-tool chatwork send ROOM MESSAGE
animaworks-tool chatwork messages ROOM [-n 20]
animaworks-tool chatwork search KEYWORD [-r ROOM] [-n 50]
animaworks-tool chatwork unreplied [--json]
animaworks-tool chatwork rooms
animaworks-tool chatwork mentions [--json]
animaworks-tool chatwork delete ROOM MESSAGE_ID
animaworks-tool chatwork sync [ROOM]
animaworks-tool chatwork <サブコマンド> ... --as <identity>
```
## Notes

- Operates with your own dedicated token `CHATWORK_API_TOKEN__<自分の名前>`. Not available if unregistered
- `--as <identity>` can only be used when delegated via `chatwork_tool.grants`. With read delegation, write (send/delete, etc.) is not possible
- Rooms can be specified by either room name or room ID