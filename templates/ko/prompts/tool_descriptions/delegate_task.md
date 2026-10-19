【중요】직속 부하인 Anima에게 작업을 위임한다 (부하의 TaskExec가 실행한다. 당신 자신은 실행하지 않는다).
【쓰기 전에 읽기 (MUST)】부르기 전에 `list_tasks(status="delegated")`와 `list_tasks(status="in_progress")`를 읽고, 같은 PR / Issue / 대상을 대상으로 자신이 이미 요청한 미완료 작업이 있는지 확인한다. 있으면 새 작업을 만들지 말고, 기존 task_id를 첨부하여 담당자에게 `send_message`로 추가 지시한다. 같은 대상에 반복해서 요청할 수 있다면 subject(예: `github:owner/repo#123`)와 선택적 version(예: head SHA)도 지정한다. 같은 상대·같은 subject·version의 미완료 요청이 있으면 시스템이 새로 만들지 않고 기존 task_id를 반환한다.
【쓴 후에 읽기 (MUST)】돌아온 task_id를 `list_tasks`로 읽어 되돌리고, summary에 대상(예: `[PR #5215]`)이 들어가 등록되었는지 확인한다. summary의 맨 앞에는 반드시 `[PR #N]` / `[Issue #N]` / 대상명을 붙인다. 반환된 JSON의 deduplicated가 true이면 새 작업이 만들어지지 않고 기존 요청에 통합되었다(DM은 전송되지 않는다).
instruction은 자기 완결적으로 만든다 (TaskExec는 대화 기록을 가지지 않는다). PR 번호 · URL · 고쳐주었으면 하는 점 · 완료의 기준만을 쓰고, 절차 조건이나 대장의 상태어로 묶지 않는다.
