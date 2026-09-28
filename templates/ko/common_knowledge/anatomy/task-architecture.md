# 정본 작업의 아키텍처

## 영속적인 정본은 하나

LLM 작업의 정본은 호스트가 관리하는 TaskStore입니다. 작업 ID, 완전한 실행 입력, 의존성, 결과, 실행 시도, 위임 별칭, 영속적인 기상 알림을 필요한 단위로 일괄 확정합니다. 별도의 파일 실행 큐와 상급자 장부를 대조하는 구성이 아닙니다.

확인은 `list_tasks` / `task_tracker`, 변경은 `submit_tasks` / `delegate_task` / `update_task`를 사용합니다. DB나 작업 파일을 직접 편집하지 않습니다. `backlog_task`는 추적 전용 작업을 등록하며 실행 권한은 획득하지 않습니다.

## 실행 계약

1. 신규 `submit_tasks`은 작업과 완전한 입력을 원자적으로 공개합니다. 원지침, 제약, workspace, 완료 조건을 보존합니다.
2. 호스트가 의존성을 확인하고 고유한 시도 토큰으로 실행 권한을 획득합니다. `in_progress`을 설정하는 것은 호스트뿐입니다.
3. 에이전트는 `update_task`로 `done` / `pending` / `cancelled`를 선언합니다. 오래된 시도는 새로운 시도의 완료나 수락된 결과를 덮어쓸 수 없습니다.
4. 의존 대상의 완료와 영속적인 기상은 호스트가 처리하며 정기 Heartbeat를 필요로 하지 않습니다. 취소, 비정상 종료, 중단은 증적과 대응 필요 사유를 남깁니다.
5. 중단된 작업은 맹목적으로 재시도하지 않습니다. 이미 완료된 작업을 확인하고 원인을 해결한 후, `submit_tasks(..., tasks=[{"task_id": "ID", "resume": true}])`으로 동일한 미종료 작업을 명시적으로 재개합니다. 입력과 이력은 보존됩니다. resume 없는 재배포는 멱등입니다.

상급자의 위임 뷰는 부하의 정본 작업에 대한 별칭입니다. 별도의 가변 장부나 Heartbeat 동기화를 거치지 않고 양쪽에 최신 상태가 반영됩니다. 의존 대상의 종료가 성공을 의미하는 것은 아니며, 취소된 것을 done으로 간주해 후속 작업을 진행시키지 않습니다.

## 작업 문맥과 증적

`state/current_state.md`은 간결한 작업 문맥이며 작업의 정본이 아닙니다. 관찰, 계획, 블로커를 남기고 일반적인 세션 경계에서는 보존합니다. 항구 지식과 절차는 전용 메모리 영역에 저장합니다.

TaskExec의 결과 요약은 `state/task_results/{task_id}/{attempt_token}.md`에 두고 TaskStore가 수락된 결과를 선택합니다. 파일 이름이나 오래된 요약만으로 완료를 증명할 수 없습니다. 활동 로그와 원지침을 증적으로 보존합니다.

## 이전 저장 위치와 명령 작업

이전 `state/task_queue.jsonl`과 `state/pending/`은 마이그레이션, 내보내기용 증적만 있으며 보존합니다. 마이그레이션은 이전 쓰기 처리의 종료와 백업 후 운영자가 명시적으로 수행합니다. 임의의 읽기로 가동 중인 이전 데이터를 가져오지 않습니다.

장시간 명령 도구는 별개입니다. `animaworks-tool submit`는 계속해서 `state/background_tasks/pending/`을 사용하며 BackgroundTaskManager가 명령 상태, 알림을 저장합니다. LLM 작업의 변경을 이유로 이 파일 경로를 제거하지 않습니다.

도구 예시는 `reference/operations/task-management.md`, 명령 실행은 `operations/background-tasks.md`를 참조하세요.
