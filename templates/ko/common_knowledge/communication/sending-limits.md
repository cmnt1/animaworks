# 메시지 및 Inbox 운영 가이드

메시지 전달, Inbox 시작, 대화 루프 방지 동작을 정리한다.
기존 전역 발신 예산, 깊이 초과 발신 차단, Inbox 쿨다운 / 캐스케이드 / intent 필터는 폐지되었다.

## 남아 있는 발신 규칙

- `send_message`의 intent는 `report` 또는 `question`이어야 한다. 작업 위임에는 `delegate_task`를 사용한다.
- 한 run에서 같은 수신처에 DM을 한 번만 보낼 수 있다. 중복 방지 규칙이며 수신처 수 상한은 없다.
- 한 run에서 같은 Board 채널에는 `post_channel`을 한 번만 게시할 수 있다. 다음 run에서는 같은 채널에 다시 게시할 수 있다.
- 시간·일 단위 발신 예산이나 페어별 대화 깊이에 따른 발신 차단은 없다.
- 내부 Anima 간 대화 깊이는 진단 목적으로 로그에 기록될 수 있다. 이는 관측 전용이며 발신을 거부하거나 메시지 본문을 버리지 않는다.

## 확인·감사 인사에 대한 응답

수신 메시지가 확인, 감사, 칭찬뿐이라면 답장하지 않는다. 응답을 이어 가지 말고 추가 질문·요청·새 정보가 있을 때만 필요한 처리를 한다.
작업 요청에 대한 접수 안내가 유용하다면 한 번만 답하고 다음 행동이나 예상 시간을 함께 전달한다.

## Inbox 시작 및 처리

Inbox JSON 파일이 새로 생기면 파일 변경 알림으로 watcher를 깨우고, 읽지 않은 메시지가 있으면 처리를 시작한다.
Inbox 작업은 동시에 하나만 실행한다. 실행 중 도착한 메시지는 다음 한 번의 처리로 모은다.
파일 알림을 놓친 경우를 위한 안전망으로 45초마다 다시 확인한다. Provider 오류가 발생하면 `rate_guard`의 복구 시간을 기다리며 읽지 않은 메시지는 남겨 둔다.

메시지가 많을 때 `state/overflow_inbox/`로 옮기는 기능은 용량 보호로 유지된다. 발신자나 intent에 따라 억제하는 것이 아니며, overflow된 메시지는 나중에 확인하고 처리할 수 있다.

## 기록 및 문제 해결

`Messenger.send`는 발신 메시지를 activity log에 기록한다. 내부 Anima 대화가 짧은 시간에 이어지면 진단용 깊이 로그가 추가될 수 있지만 전달 결과에는 영향을 주지 않는다.
최근 `message_sent` / `channel_post` 이벤트는 `core/memory/priming/outbound.py`가 priming에 사용한다.

메시지가 전달되지 않으면 수신처 해결, 권한, 외부 채널의 실제 전송 오류를 확인한다. 기다려야 하는 발신 예산이나 대화 깊이 제한은 없다.

## 구현 위치

| 역할 | 모듈 |
|------|------------|
| 수신처 해결 및 Slack / Chatwork 외부 전송 | `core/messaging/outbound.py` |
| 내부 DM 전달, activity log 기록, 진단용 깊이 로그 | `core/messaging/messenger.py` |
| DM 중복 방지 및 run 내 Board 채널 중복 방지 | `core/tooling/handler_comms.py` |
| Inbox 파일 wake, 단일 실행 조정, provider backoff | `core/supervisor/inbox_rate_limiter.py` |
| overflow 파일을 통한 Inbox 용량 보호 | `core/anima/inbox_overflow.py` |
| 최근 발신의 프롬프트 주입 | `core/memory/priming/outbound.py` |
