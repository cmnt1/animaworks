---
name: gmail-tool
description: >-
  Gmail integration tool. It checks unread emails, retrieves message bodies, and creates drafts via the Gmail API using OAuth2.
  Use when: Use when: you need to check received emails, read message bodies, create drafts, search the inbox, or handle labeled emails.
tags: [communication, gmail, email, external]
---
Understood. Please provide the Japanese content you’d like me to translate.# Gmail Tool

An external tool that directly operates on Gmail emails using OAuth2.## How to Call

**Bash**: Run with `animaworks-tool gmail <サブコマンド> [引数]`## List of Actions### unread — Unread Mail List
```bash
animaworks-tool gmail unread [-n 20]
```
### read_body — Read Email Body
```bash
animaworks-tool gmail read MESSAGE_ID
```
### draft — Draft Creation
```bash
animaworks-tool gmail draft --to ADDR --subject SUBJ --body BODY [--thread-id TID]
```
## CLI Usage

```bash
animaworks-tool gmail unread [-n 20]
animaworks-tool gmail read MESSAGE_ID
animaworks-tool gmail draft --to ADDR --subject SUBJ --body BODY [--thread-id TID]
```
## Notes

- OAuth2 authentication flow is required on first use
- credentials.json and token.json must be placed in ~/.animaworks/