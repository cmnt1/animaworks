---
name: gmail-tool
description: >-
  Gmail 연동 도구. OAuth2로 Gmail API를 통해 읽지 않은 메일 확인, 본문 가져오기, 초안 작성을 수행한다.
  Use when: 메일 수신 확인, 본문 읽기, 초안 작성, 받은 편지함 검색, 라벨이 있는 메일 조작이 필요할 때.
tags: [communication, gmail, email, external]
---


# Gmail 도구

Gmail 메일을 OAuth2로 직접 조작하는 외부 도구.

## 호출 방법

**Bash**: `animaworks-tool gmail <サブコマンド> [引数]` 로 실행

## 작업 목록

### unread — 읽지 않은 메일 목록
```bash
animaworks-tool gmail unread [-n 20]
```

### read_body — 메일 본문 읽기
```bash
animaworks-tool gmail read MESSAGE_ID
```

### draft — 초안 작성
```bash
animaworks-tool gmail draft --to ADDR --subject SUBJ --body BODY [--thread-id TID]
```

## CLI 사용법

```bash
animaworks-tool gmail unread [-n 20]
animaworks-tool gmail read MESSAGE_ID
animaworks-tool gmail draft --to ADDR --subject SUBJ --body BODY [--thread-id TID]
```

## 주의 사항

- 최초 사용 시 OAuth2 인증 흐름 필요
- credentials.json 와 token.json 가 ~/.animaworks/ 에 배치되어야 함
