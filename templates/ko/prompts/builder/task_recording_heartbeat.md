### Heartbeat 작업 기록

- 계속 작업은 `pending`으로 읽고 같은 task_id로 `submit_tasks`에 제출하여 이미 승인된 범위를 계속하세요. 모든 완료 조건의 증거를 확인한 후에만 `done`으로 설정하세요
- Anima 간의 위임도 작업 큐에 기록하고 relay_chain을 업데이트하세요
- 작업 완료 시 `update_task`로 상태를 업데이트하세요
