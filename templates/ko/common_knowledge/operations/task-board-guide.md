# TaskBoard와 사람을 위한 보고

## 정본과 표시

TaskBoard는 정본 태스크와 표시용 metadata를 투영합니다.
상태는 `list_tasks(detail=true)` / `task_tracker()`로 확인합니다.
`state/current_state.md`는 작업 문맥, `state/task_results/`는 실행 시도 결과이며 별도 실행 원장이 아닙니다.
표시 열·snooze·archive는 작업 결과나 취소를 대신하지 않습니다.

## 수기 이중 관리 줄이기

위임·완료·Heartbeat마다 `shared/task-board.md`를 다시 쓸 의무는 없습니다.
사람이 요청한 보고는 정본의 필요한 범위를 참조하여 작성 시각과 미확인 사항을 명시합니다.
기존 보고서를 승인 없이 삭제하거나 매주 초기화하지 않습니다. 보고 상태만으로 작업을 재제출하지 않습니다.

## 외부 공유

Slack 게시·수정은 사람의 요청이나 기존에 허용된 운영이 있을 때만 수행합니다.
`slack_channel_post` / `slack_channel_update` 권한과 승인 조건을 지키고 회사 경계, 기밀 범위,
이미 게시한 내용을 확인합니다. 자동 게시나 알림을 새로 늘리지 않습니다.

## CLI 읽기 및 쓰기

`animaworks-tool task board [--anima NAME | --all] [--stale DAYS] [--limit N]`으로 진행 중인 작업을 나열하고,
`task show ID`로 상세 정보를 확인합니다. `task claim ID [--ttl 30m]`로 lease를 획득하고,
`task note ID TEXT`로 메모를 추가하고, `task done ID --note TEXT`로 완료 처리하고,
`task cancel ID --reason REASON`으로 취소하고, `task release ID`로 lease를 해제합니다.
기계가 읽을 출력이 필요하면 `board` 또는 `show`에 `--json`을 붙이세요.

lease는 보유자가 다른 anima의 작업을 종료하거나 메모를 남길 수 있게 하는 시간 제한 잠금입니다.
보유 중에만 변경할 수 있으며 기본 30분 후 자동 만료됩니다. 다른 사람이 lease를 보유하지 않았다면
담당자는 lease 없이 자신의 작업을 변경할 수 있습니다.
판단은 anima가 하며, 기계가 작업을 자동으로 종료하지 않습니다.
