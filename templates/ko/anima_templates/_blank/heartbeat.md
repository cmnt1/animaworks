# Heartbeat: {name}

## 활동 시간
24시간 (서버 설정 시간대)

## 현재 시각
시스템 프롬프트의 `現在時刻` 필드 값을 사용할 것. 이력이나 스케줄에서 추측하지 말 것.

## 관찰 규칙
- `status: ok` 의 `Current Pre-Observed Heartbeat Snapshot` 이 있으면, Inbox / task_queue / current_state / state/pending / state/task_results / background_notifications / peer_activity / recent_own_files 의 확인 근거로 도구를 겹쳐서 호출하지 않는다. 사전 관찰이 없으면 `heartbeat_observe_snapshot` 를 폴백으로 호출한다
- 일반 Heartbeat에서는, 위 고정 스코프 확인을 위해 shell / `rtk proxy` / `Get-Content` / `ls` 를 사용하지 않는다
- 어느 snapshot 경로에서도 `status: ok` 을 얻을 수 없는 경우에만, 같은 blocked 경로를 반복하지 않고, 블로커로 기록하거나 보고한다

## 체크리스트
- Inbox에 읽지 않은 메시지가 있는가
- 진행 중 작업에 블로커가 발생하지 않았는가
- 자신의 작업 영역에 새 파일이 놓이지 않았는가
- 아무것도 없으면 아무것도 하지 않는다 (HEARTBEAT_OK)

## 알림 규칙
- 긴급하다고 판단한 경우 관계자에게 알림
- 상급자가 없는 경우, 부하로부터 도착한 성과는 요점만 사용자에게 call_human 으로 전달한다
- 같은 내용의 알림은 24시간 이내에 반복하지 않는다
