---
name: slack-tool
description: >-
  Slack 연동 도구. 메시지 송수신·검색·미답변 확인·채널 목록·이모지 반응을 수행한다.
  Use when: Slack에 게시, 채널 목록, 스레드 답장, 미답변 확인, 반응 추가가 필요할 때.
tags: [communication, slack, external]
---
Understood. Please provide the Japanese content you would like me to translate into Korean.# Slack 도구

Slack의 메시지 송수신, 검색, 리액션을 수행하는 외부 도구.## 호출 방법

**Bash**: `animaworks-tool slack <サブコマンド> [引数]`에서 실행## 작업 목록### send — 메시지 전송
```bash
animaworks-tool slack send CHANNEL MESSAGE [--thread TS]
```
### messages — 메시지 가져오기
```bash
animaworks-tool slack messages CHANNEL [-n 20]
```
### 검색 — 메시지 검색
```bash
animaworks-tool slack search KEYWORD [-c CHANNEL] [-n 50]
```
### unreplied — 미답신 메시지 확인
```bash
animaworks-tool slack unreplied [--json]
```
### channels — 채널 목록
```bash
animaworks-tool slack channels
```
### react — 이모지 리액션
- `emoji`: Slack의 이모지 이름(콜론 없음. 예: `thumbsup`, `eyes`, `white_check_mark`)
- `message_ts`: 리액션 대상 메시지의 타임스탬프(`messages` 액션의 결과에서 얻을 수 있음)
- **주의**: `react` 액션은 CLI 미지원. MCP를 통해 사용한다.## CLI 사용법

```bash
animaworks-tool slack send CHANNEL MESSAGE [--thread TS]
animaworks-tool slack messages CHANNEL [-n 20]
animaworks-tool slack search KEYWORD [-c CHANNEL] [-n 50]
animaworks-tool slack unreplied [--json]
animaworks-tool slack channels
```
## 주의사항

- Slack Bot Token은 credentials에 사전 설정이 필요합니다
- 채널은 #이 붙은 이름 또는 채널 ID로 지정합니다
- 리액션에는 `reactions:write` 스코프가 필요합니다