# 작업 보드와 인간 대상 보고

## 정본과 표시

TaskBoard는 정본 작업과 표시용 메타데이터로 구성된다.
상태 확인은 `list_tasks(detail=true)` / `task_tracker()`을 사용한다.
`state/current_state.md`는 작업 문맥, `state/task_results/`은 시행 결과이며, 별도의 실행 원장이 아니다.
표시 열·아카이브는 실행 결과나 취소를 대신하지 않는다.

## 수기 이중 관리 금지

각 위임·완료·Heartbeat 때마다 `shared/task-board.md`을 다시 쓸 의무는 없다.
인간이 요청한 사안 보고는 만들어도 되지만, 정본에서 필요한 범위를 참조하고 작성 시각과 미확인 사항을 명시한다.
기존 보고 파일은 승인 없이 삭제하거나 주간 리셋하지 않는다. 보고 상태만으로 작업을 다시 투입하지 않는다.

## 외부 공유

Slack 게시·업데이트는 인간의 요청 또는 기존에 허용된 운영이 있는 경우에만 수행한다.
`slack_channel_post` / `slack_channel_update`의 권한과 승인 조건을 지키고,
회사 경계·기밀 범위·이미 게시된 내용을 확인한다. 자동으로 새 게시나 알림을 늘리지 않는다.

## CLI에서 읽기와 쓰기

`animaworks-tool task board [--anima NAME | --all] [--stale DAYS] [--limit N]`으로 미완료 작업을 목록화하고,
`task show ID`로 세부 내용을 확인한다. `task claim ID [--ttl 30m]`로 lease를 획득하고,
`task note ID TEXT`으로 주석, `task done ID --note TEXT`로 완료,
`task cancel ID --reason REASON`로 취소, `task release ID`으로 lease를 해제한다.
JSON이 필요하면 `board` / `show`에 `--json`를 붙인다.

lease는 다른 사람의 작업을 닫거나 주석을 달기 위한 기한부 잠금이다. 획득 중에만 변경할 수 있고, 기본 30분 후 자연히 만료된다.
자신의 작업은 다른 사람의 lease가 없으면 lease 없이도 변경할 수 있다.
보고 판단하는 것은 anima이며, 기계는 작업을 자동으로 닫지 않는다.
소유자의 판단은 작업 본문에 있는 "취소 없음", "pending 유지" 등의 과거 지정보다 우선한다.
소유자가 자신의 작업을 `done` / `cancel`하면 위임한 anima에게 이유와 함께 자동 알림이 간다. 위임자는 같은 작업을 다시 내기 전에 이 알림을 확인한다.
