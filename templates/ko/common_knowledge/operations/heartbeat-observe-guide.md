# Heartbeat Observe Guide

Heartbeat Observe는 상태 확인과 계획 판단을 위한 가벼운 관찰 단계입니다. 일반 Heartbeat에서는 실제 작업, 긴 조사, 임의 파일 탐색, shell 기반 상태 확인을 수행하지 않습니다.

## 규칙

- MUST: `status: ok`인 `Current Pre-Observed Heartbeat Snapshot`이 있으면 이를 사용하고 도구를 다시 호출하지 않습니다. 사전 관찰이 없으면 폴백으로 Observe 시작 시 `heartbeat_observe_snapshot`을 호출합니다.
- MUST: Inbox, task_queue, current_state, state/pending, state/task_results, background_notifications, peer_activity, recent_own_files는 `heartbeat_observe_snapshot` 결과를 1차 근거로 사용합니다.
- MUST NOT: 위 고정 위치 확인을 위해 Bash / shell / `rtk proxy` / `Get-Content` / `ls` / `read_file` / `list_directory`를 사용하지 않습니다.
- MUST NOT: Heartbeat 관찰값, 시각, 건수, 판단 로그를 TaskBoard 작업 제목에 넣지 않습니다. 기록이 필요하면 기존 작업의 context / task_results / activity_log에 남깁니다.
- MUST: 사전 관찰과 직접 호출 모두에서 `status: ok`를 얻지 못한 경우에만 같은 blocked 경로를 반복하지 말고, `state/current_state.md`에 블로커로 기록하거나 필요 시 보고합니다.

## HEARTBEAT_OK 조건

`HEARTBEAT_OK`는 사전 관찰 또는 `heartbeat_observe_snapshot` 직접 호출로 고정 범위 관찰을 완료했고, 미처리 지시, STALE/OVERDUE 작업, 미실행 pending, 미확인 task_results, 보고해야 할 블로커가 없을 때만 반환합니다.

## 추가 확인

snapshot 범위 밖의 외부 서비스, Board, Slack, GitHub, Web 등을 확인해야 할 때만 해당 전용 도구를 사용합니다. 고정 범위 관찰의 대체로 shell을 사용하지 않습니다.
