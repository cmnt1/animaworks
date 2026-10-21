# Heartbeat Observe 가이드

Heartbeat Observe는 상태 확인과 계획 판단을 위한 경량 관측 단계입니다. 일반적인 실작업, 긴 조사, 임의 파일 탐색, shell을 통한 상태 확인은 하지 않습니다.

## 원칙

- MUST: `status: ok`의 `Current Pre-Observed Heartbeat Snapshot`이 있으면 그것을 사용하고 도구를 중복 호출하지 않는다. 사전 관측이 없으면 폴백으로 Observe의 처음에 `heartbeat_observe_snapshot`를 호출한다.
- MUST: Inbox, task_queue, current_state, state/pending、state/task_results、background_notifications、peer_activity、recent_own_files은 `heartbeat_observe_snapshot`의 결과를 일차 근거로 한다.
- MUST NOT: 위의 고정 스코프 확인을 위해 Bash / shell / `rtk proxy` / `Get-Content` / `ls` / `read_file` / `list_directory`을 사용하지 않는다.
- MUST NOT: Heartbeat의 관측값, 시각, 건수, 판단 로그를 TaskBoard의 작업 이름으로 하지 않는다. 필요하면 기존 작업의 context / task_results / activity_log에 붙인다.
- MUST: 사전 관측과 직접 호출 중 어느 쪽에서도 `status: ok`를 얻을 수 없는 경우에만, 같은 blocked 경로를 반복하지 않고 블로커로서 `state/current_state.md`에 기록하거나 필요에 따라 보고한다.

## HEARTBEAT_OK의 조건

`HEARTBEAT_OK`은 사전 관측 또는 `heartbeat_observe_snapshot`의 직접 호출에 의한 고정 스코프 관측을 완료하고, 미처리 지침, 마감일이 지난 작업, 미실행 pending, 미확인 task_results, 보고해야 할 블로커가 없는 경우에 한한다.

## 추가 확인

snapshot 밖에 있는 외부 서비스, Board, Slack, GitHub, Web 등을 확인할 필요가 있는 경우에만 해당 전용 도구를 사용한다. 고정 스코프의 대체로서 shell을 사용해서는 안 된다.
