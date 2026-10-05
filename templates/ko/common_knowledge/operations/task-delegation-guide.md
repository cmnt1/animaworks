# 작업 투입과 위임

## 실행 경로

Agent/Task의 네이티브 하위 에이전트 시작은 사용하지 않고, 공개된 작업 도구를 사용한다.
일반 채팅으로 완료할 수 있는 일은 직접 실행한다. 지속 추적만 필요하면 `backlog_task`,
자신의 백그라운드 실행은 `submit_tasks`, 유효한 직속 부하에게 위임은
`delegate_task(name="担当名", instruction="原指示と完了条件", summary="要約")`.
도구의 제공 범위와 권한에 따라, 유효하지 않은 담당자에게 위임하거나 무단으로 다른 경로로 전환하지 않는다.
Heartbeat는 판단·투입에 사용하고, 장시간의 실제 작업은 TaskExec에 넘긴다.

## 인계할 정보

실행자는 대화 기록을 자동으로 공유하지 않는다. 원래 지침, 목적, 관련 파일과 아는 범위의 위치,
현재 상태, 완료 조건, 승인 조건, 금지 사항을 전달한다. 존재하지 않는 경로나 줄 번호는 만들지 않는다.
`description`과 `context`, `acceptance_criteria`, `constraints`, `file_paths`를 용도에 따라 사용한다.
모델과 등록된 workspace 지정도 유지한다. 다른 Anima의 개인 디렉터리에 쓰기를 지시하지 않는다.

`submit_tasks(batch_id="work", tasks=[{"task_id":"job","title":"仕事","description":"具体的な依頼"}])`
는 작업과 실행 입력을 일괄 공개한다. 같은 ID의 재전송은 재실행이 아니다.
`parallel:true`은 worker 수의 상한 내에서 병렬 가능, `depends_on`은 선행 작업의 완료와 시도 종료를 기다린다.
의존 대상이 취소·미완료라면 확인이 필요하며, 성공했다고 추측하지 않는다.

## 상태·결과·재개

상태는 `list_tasks(detail=true)`, 위임 추적은 `task_tracker()`로 확인한다.
추적 ID는 부하가 소유하는 같은 작업의 별칭이며, 원장 동기화나 파일 구제는 필요 없다.
`task_tracker(status="all")`는 전체 건, `status="completed"`은 done/cancelled。
실행 권한과 `in_progress`는 호스트가 관리한다. 결과는 근거가 있는 `done`,
구체적인 대기 이유가 있는 `pending`, 명시적인 중단의 `cancelled`로 선언한다.

미완료 알림을 받으면 이미 처리된 외부 작업과 성과를 확인하고, 계속이 적절할 때만
`submit_tasks(batch_id="resume-job", tasks=[{"task_id":"job","resume":true}])`로 저장된 입력을 재사용한다.
실행 중·완료·취소된 작업은 이 방법으로 재개할 수 없다. 무한 재투입을 하지 않는다.
결과 요약은 `state/task_results/{task_id}/{attempt_token}.md`. 파일 존재만으로 완료로 취급하지 않는다.

## 중복과 보고

같은 요청의 미완료 작업이 있다는 것을 알고 있다면, 그 ID에 추가 정보를 전달한다.
중복 의심만으로 오래된 작업을 자동 취소·덮어쓰지 않고, 담당자와 실행 상태를 확인한다.
필요한 승인·독립 리뷰는 유지한다. 결과는 판단이 필요한 요청자에게 보고하고, 전 계층으로
같은 내용을 전송하거나 별도의 수기 원장에 이중 기록하는 것을 필수로 하지 않는다.
저장 세부 사항은 `common_knowledge/anatomy/task-architecture.md`을 참조한다.
