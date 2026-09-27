---
name: discord-tool
description: >-
  Discord 연동 도구. 메시지 전송·수신·검색·길드·채널 목록·리액션을 수행합니다.
  Use when: Discord에서 메시지 전송, 채널 목록, 서버 내 검색, 리액션, 스레드 확인이 필요할 때.
tags: [communication, discord, external]
---
Understood. Please provide the Japanese content you would like me to translate into Korean.# Discord 도구

Discord의 메시지 송수신·검색·서버/채널 목록·리액션을 수행하는 외부 도구.## 호출 방법

**Bash**: `animaworks-tool discord <サブコマンド> [引数]`에서 실행## 작업 목록### guilds — 서버 목록
```bash
animaworks-tool discord guilds
```
### channels — 채널 목록
```bash
animaworks-tool discord channels GUILD_ID
```
- `GUILD_ID`: 대상 길드(서버)의 Snowflake ID (필수)### send — 메시지 전송
```bash
animaworks-tool discord send CHANNEL_ID MESSAGE [--reply-to MESSAGE_ID]
```
- `CHANNEL_ID`: 전송 대상 텍스트 채널의 Snowflake ID
- `--reply-to`: 선택 사항. 답장 대상 메시지 ID### messages — 메시지 가져오기
```bash
animaworks-tool discord messages CHANNEL_ID [-n 20]
```
### 검색 — 메시지 검색
```bash
animaworks-tool discord search KEYWORD [-c CHANNEL_ID] [-n 50]
```
### react — 반응 (MCP 경유 전용, CLI 미지원)
- 이모지 반응 추가. **MCP 경유 전용**. CLI에서는 사용할 수 없음.## CLI 사용법

```bash
animaworks-tool discord guilds
animaworks-tool discord channels GUILD_ID
animaworks-tool discord send CHANNEL_ID MESSAGE [--reply-to MESSAGE_ID]
animaworks-tool discord messages CHANNEL_ID [-n 20]
animaworks-tool discord search KEYWORD [-c CHANNEL_ID] [-n 50]
```
## 주의사항

- Discord Bot Token은 credentials에 사전 설정이 필요합니다
- 채널 ID는 Discord의 개발자 모드에서 우클릭 → 「ID 복사」로 획득합니다
- 메시지는 2000자 제한이 있습니다
- 길드 ID·채널 ID·메시지 ID는 모두 숫자 문자열(Snowflake ID)입니다
- Bot에는 필요한 권한(Send Messages, Read Message History, Add Reactions, View Channels)이 필요합니다