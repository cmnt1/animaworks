【중요】직속 부하인 Anima에게 작업을 위임한다(부하의 TaskExec가 실행한다. 당신 자신은 실행하지 않는다).
【작성 전에 읽기(MUST)】호출하기 전에 `list_tasks(status="delegated")`와 `list_tasks(status="in_progress")`을 읽고, 동일한 PR / Issue / 대상에 대해 내가 이미 요청한 미완료 작업이 있는지 확인한다. 있다면 새 작업을 만들지 말고 기존 task_id를 첨부해 담당자에게 `send_message`로 추가 지시한다. 동일한 대상에 반복해서 요청할 가능성이 있다면 subject(예: `github:owner/repo#123`)와 선택적 version(예: head SHA)도 지정한다. 동일한 상대·동일한 subject·version의 미완료 요청이 있으면 시스템은 새로 만들지 않고 기존 task_id를 반환한다.
【작성 후에 읽기(MUST)】반환된 task_id를 `list_tasks`로 다시 읽어 summary에 대상(예: `[PR #5215]`)이 포함되어 등록되어 있는지 확인한다. summary의 맨 앞에는 반드시 `[PR #N]` / `[Issue #N]` / 대상명을 붙인다. 반환된 JSON의 deduplicated가 true이면 새 작업은 만들어지지 않고 기존 요청에 통합된 것이다(DM은 전송되지 않는다).
instruction은 자체 완결형으로 작성한다(TaskExec는 대화 기록을 갖고 있지 않다). PR 번호·URL·수정할 점·완료 기준만 작성하고, 절차 조건이나 대장의 상태 용어로 제약하지 않는다.
