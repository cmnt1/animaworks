# call_human 가이드 — 사람에게 알리기와 답장 수신

## 개요

`call_human`은 사람 관리자에게 알림을 보내는 도구입니다. **일방통행이 아닙니다** — 사람이 Slack 스레드에서 답장하면, 그 답장은 발신 Anima의 Inbox에 자동 배달됩니다.

## 전송

```
call_human(
    subject="제목",
    body="본문 (상황, 시도한 내용, 요청 사항을 포함)",
    priority="normal"  # "normal" | "high" | "urgent"
)
```

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `subject` | MUST | 제목 (간결하게) |
| `body` | MUST | 본문 (상황, 시도한 내용, 요청을 포함) |
| `priority` | MAY | `normal` (기본), `high`, `urgent` |

### 사용 시점

- 긴급도가 "높음"인 문제 (데이터 손실 위험, 보안, 서비스 중단)
- 자신의 판단 범위를 넘는 결정이 필요한 경우
- 최상위 Anima에서 상사가 없는 경우의 에스컬레이션

상세 판단 기준은 `troubleshooting/escalation-flowchart.md`를 참조하세요.

### 레이트 제한

- `call_human`은 DM 레이트 제한 (30/h, 100/day)의 **대상 외**
- 긴급 시에도 제한 걱정 없이 전송 가능

## 답장 수신

### 구조

1. `call_human`으로 알림을 보내면 Slack에 메시지가 게시됨
2. 사람이 해당 메시지의 **스레드 (thread)**에서 답장
3. 답장이 발신 Anima의 Inbox에 자동 라우팅됨
4. 다음 Inbox 처리 사이클 (보통 2초 이내 감지)에서 답장이 처리됨

### 답장 메시지 속성

수신한 답장 메시지의 속성:

- `source`: `"slack"` (Slack 경유 답장)
- `from_person`: `"slack:U..."` 형식 (Slack 사용자 ID)
- 일반 Inbox 메시지와 동일하게 처리됨

### 답장을 기다리는 경우

`call_human`을 보낸 후 답장을 기다려야 하는 경우:

1. 대기 상태를 `state/current_state.md`에 기록
2. 답장은 다음 Inbox 처리에서 자동으로 도착
3. 즉시 답장이 없어도 사람이 답장한 시점에 자동 배달됨

### 답장에 응답하기

답장을 받으면 일반 Inbox 메시지와 동일하게 응답할 수 있습니다. 단, 답장 상대가 Slack 사용자이므로 `send_message` 대신 채팅 응답 또는 추가 `call_human`으로 대응하세요.

## 주의 사항

- 답장 라우팅은 **Bot Token 모드** (`chat.postMessage`)로 전송된 알림에만 대응. Webhook 모드에서는 답장이 도착하지 않음 (관리자 설정 문제이며 Anima가 제어하는 것이 아님)
- 답장 매핑은 **7일간** 유지됨. 7일 이상 경과한 스레드의 답장은 전달되지 않음
- 사람의 답장이 없는 경우에도 필요하면 다시 `call_human`으로 후속 연락 가능
