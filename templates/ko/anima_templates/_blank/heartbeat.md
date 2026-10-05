# Heartbeat: {name}

## 활동 시간
24시간 (서버 설정 시간대)

## 현재 시각
시스템 프롬프트의 `現在時刻` 필드 값을 사용할 것. 기록이나 일정에서 추측하지 않는다.

## 관찰 규칙
- `status: ok`인 `Current Pre-Observed Heartbeat Snapshot`이 있으면 Inbox / task_queue / current_state / state/pending / state/task_results / background_notifications / peer_activity / recent_own_files 확인 근거로 사용하고 도구를 다시 호출하지 마세요. 사전 관찰이 없으면 `heartbeat_observe_snapshot`을 폴백으로 호출하세요
- 일반 Heartbeat에서는 위 고정 위치 확인을 위해 shell / `rtk proxy` / `Get-Content` / `ls`를 사용하지 마세요
- 두 snapshot 경로 모두에서 `status: ok`를 얻지 못한 경우에만 같은 blocked 경로를 반복하지 말고 블로커로 기록하거나 보고하세요

## 체크리스트
- Inbox에 읽지 않은 메시지가 있는지
- 진행 중인 작업에 차단 요인이 발생하지 않았는지
- 자신의 작업 영역에 새 파일이 놓여 있지 않은지
- 아무것도 없으면 아무것도 하지 않는다 (HEARTBEAT_OK)

## 알림 규칙
- 긴급하다고 판단한 경우에만 관계자에게 알림
- 같은 내용의 알림은 24시간 이내에 반복하지 않는다.
