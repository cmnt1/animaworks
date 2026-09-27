【중요】직속 부하인 Anima에게 작업을 위임한다 (부하의 TaskExec가 실행한다. 당신 자신은 실행하지 않는다).
【쓰기 전에 읽기 (MUST)】부르기 전에 `list_tasks(status="delegated")`와 `list_tasks(status="in_progress")`를 읽고, 같은 PR / Issue / 대상을 상대로 자신이 이미 요청한 미완료 작업이 있는지 확인한다. 있으면 새 작업을 만들지 말고, 기존 task_id를 첨부하여 담당자에게 `send_message`로 추가 지시한다.
【쓴 후에 읽기 (MUST)】돌아온 task_id를 `list_tasks`로 읽어 되돌리고, summary에 대상(예: `[PR #5215]`)이 들어가 등록되었는지 확인한다. summary의 맨 앞에는 반드시 `[PR #N]` / `[Issue #N]` / 대상명을 붙인다.
instruction은 자기 완결적으로 만든다 (TaskExec는 대화 기록을 갖지 않는다). PR 번호·URL·고쳐줬으면 하는 점·완료의 기준만 쓰고, 절차 조건이나 대장의 상태어로 묶지 않는다.