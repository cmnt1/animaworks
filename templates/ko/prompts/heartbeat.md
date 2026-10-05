하트비트입니다. 역할에 지정된 정기 확인을 수행하세요.

## 확인 사항
{checklist}

`status: ok`인 `Current Pre-Observed Heartbeat Snapshot`이 있으면 1차 근거로 사용하고 도구를 다시 호출하지 마세요. 사전 관찰이 없을 때만 `heartbeat_observe_snapshot`을 폴백으로 호출하세요.
고정 범위를 다시 확인하기 위해 shell / `rtk proxy` / `read_file` / `list_directory`를 사용하지 마세요.

미처리 요청, 이상 상황, 기한이 있는 작업에 필요한 조치를 선택하세요.
- 자신의 실행은 `submit_tasks`, 위임은 `delegate_task`를 사용하세요. 추가 정보는 기존 작업 ID에 연결하고 중복을 만들지 마세요. 연락·승인은 `send_message` / `call_human`으로 하고 같은 내용을 모든 관리 계층에 전달하지 마세요.
- 요청에 대응하거나 위임하거나, 대기 이유와 조건을 명시하세요.
- `animaworks-tool task board`로 대장을 점검하고, 닫을지는 담당자가 현재 상황으로 판단하세요 (상세는 `read_memory_file(path="common_knowledge/operations/task-board-guide.md")`).
- 미완료 실행 재개는 `submit_tasks`의 tasks에 `{{"task_id":"기존-ID","resume":true}}`를 지정하세요.

복구를 위한 순회나 전체 재제출은 불필요합니다. 필요한 절차·승인 조건은 참조해도 됩니다. 대응할 사항이 없으면 HEARTBEAT_OK만 반환하세요.
