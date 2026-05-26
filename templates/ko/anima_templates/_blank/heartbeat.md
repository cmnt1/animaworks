# Heartbeat: {name}

## 활동 시간
24시간 (서버 설정 타임존)

## 현재 시각
시스템 프롬프트의 현재 시각 필드 값을 사용하세요. 이력이나 스케줄에서 추측하지 마세요.

## 관찰 규칙
- 먼저 `heartbeat_observe_snapshot`을 호출하고, Inbox / task_queue / current_state / state/pending / state/task_results / background_notifications / peer_activity / recent_own_files 확인 근거로 사용하세요
- 일반 Heartbeat에서는 위 고정 위치 확인을 위해 shell / `rtk proxy` / `Get-Content` / `ls`를 사용하지 마세요
- snapshot을 사용할 수 없으면 같은 blocked 경로를 반복하지 말고 블로커로 기록하거나 보고하세요

## 체크리스트
- inbox에 읽지 않은 메시지가 있는가
- 진행 중인 작업에 블로커가 발생하지 않았는가
- 자신의 작업 영역에 새로운 파일이 배치되지 않았는가
- 아무것도 없으면 아무것도 하지 않습니다(HEARTBEAT_OK)

## 알림 규칙
- 긴급하다고 판단한 경우에만 관계자에게 알립니다
- 같은 내용의 알림은 24시간 이내에 반복하지 않습니다
