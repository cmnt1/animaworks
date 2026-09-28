---
name: chatwork-tool
description: >-
  Chatwork 연동 도구. 메시지 송수신·검색·미답변 확인·룸 목록을 수행한다.
  Use when: Chatwork에서 메시지 전송, 룸 목록 조회, 미답변 확인, 채팅 검색, 멘션 대응이 필요할 때.
tags: [communication, chatwork, external]
---


# Chatwork 도구

Chatwork의 메시지 송수신·검색·관리를 수행하는 외부 도구.

## 호출 방법

**Bash**: `animaworks-tool chatwork <サブコマンド> [引数]` 로 실행. 구문은 아래를 참조.

## 액션 목록

### send — 메시지 전송
```bash
animaworks-tool chatwork send ROOM MESSAGE
```

### messages — 메시지 조회
```bash
animaworks-tool chatwork messages ROOM [-n 20]
```

### search — 메시지 검색
```bash
animaworks-tool chatwork search KEYWORD [-r ROOM] [-n 50]
```

### unreplied — 미답변 메시지 확인
```bash
animaworks-tool chatwork unreplied [--json]
```
- `include_toall` (선택, 기본값: false): 전체 대상 메시지를 포함할지 여부

### rooms — 룸 목록
```bash
animaworks-tool chatwork rooms
```

### mentions — 멘션 조회
```bash
animaworks-tool chatwork mentions [--json]
```
- `include_toall` (선택, 기본값: false): 전체 대상 메시지를 포함할지 여부

### delete — 메시지 삭제 (자신의 발언만)
```bash
animaworks-tool chatwork delete ROOM MESSAGE_ID
```

### sync — 메시지 동기화 (캐시 업데이트)
```bash
animaworks-tool chatwork sync [ROOM]
```

## CLI 사용법

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

## 주의사항

- 자신 전용 토큰 `CHATWORK_API_TOKEN__<自分の名前>` 으로 동작. 미등록 시 사용 불가
- `--as <identity>` 은 `chatwork_tool.grants` 로 위임된 경우에만 이용 가능. read 위임에서는 write (send/delete 등)는 불가
- room은 룸 이름으로도 룸 ID로도 지정 가능
