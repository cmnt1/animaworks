# 작업 관리 방법

## 정본은 하나

확인에는 `list_tasks(detail=true)` 또는 `animaworks-tool task list`을 사용한다. 호스트 관리 TaskStore에 지침·의존 관계·실행 시도·결과·위임 별칭을 영속화한다. 데이터베이스 직접 편집, 실행 권한 위조, 파일을 써서 큐를 복구하는 것은 금지. 기존 `state/task_queue.jsonl`와 `state/pending/`은 마이그레이션·내보내기용 증적이며, 운영 중 투입 대상이 아니다. 운영자의 마이그레이션을 위해 보존한다.

일반 채팅으로 처리할 수 있는 요청은 직접 대응해도 된다. 백그라운드 실행·병렬화·지속 추적이 필요한 경우에만 작업을 등록한다. 인간 유래 요청을 최우선으로 하고, 동등한 우선순위라면 상급자의 요청을 동료보다 우선한다. 인계에서는 원지침·완료 조건·제약·필요한 맥락을 유지한다.

## 실행 경로를 선택한다

- Inbox는 메시지와 가벼운 답변을 처리한다.
- Heartbeat는 의미 있는 변화를 확인하고 대응을 판단한다. 장시간 코딩이나 대량의 도구 실행은 하지 않고, 자신의 TaskExec에는 `submit_tasks`, 직속 부하에게는 `delegate_task`을 사용한다.
- TaskExec는 영속화된 작업을 도구와 함께 실행한다. 실행 권한 획득, 병렬 수, 의존 관계, 취소, 시도의 복구는 호스트가 관리하며, 정기 Heartbeat에 의존하지 않는다.
- Agent/Task의 서브에이전트 시작 도구는 무효. 위의 투입·위임 도구를 사용한다.

## 투입과 확인

`submit_tasks`의 실행자는 부하가 아니라 **자신의 TaskExec**.

```
submit_tasks(batch_id="report-build", tasks=[
  {"task_id": "collect", "title": "根拠収集", "description": "依頼された根拠を出典付きで収集する。", "parallel": true},
  {"task_id": "report", "title": "報告作成", "description": "収集結果から依頼された報告書を作る。", "depends_on": ["collect"]}
])
list_tasks(detail=true)
```

새 작업에는 `task_id`, `title`, `description`가 필요하다. 임의 항목은 `context`, `acceptance_criteria`, `constraints`, `file_paths`, `workspace`, `parallel`, `depends_on`, `reply_to`, `model`. `workspace`는 등록된 작업 공간의 별칭. 모델 선택은 일반적으로 런타임 설정을 따른다. 긴 원지침을 짧은 요약으로 대체하지 않는다.

투입 시 배치를 검증하고, 작업과 실행 입력을 일괄 확정한다. 같은 투입의 재전송은 멱등이며, 재시도가 아니다. 의존 대상이 정상 완료될 때까지 후속은 실행되지 않는다. 파일 부재나 `pending` 표시만으로 실행 가능하다고 판단하지 않는다.

## 결과 선언과 명시적 재개

```
update_task(task_id="TASK_ID", status="done", summary="検証済みの結果", result="根拠と成果物の場所")
update_task(task_id="TASK_ID", status="pending", summary="指定した入力を待っている")
update_task(task_id="TASK_ID", status="cancelled", summary="不要になった理由")
```

`in_progress`는 실행 권한 획득 시 호스트가 설정하는 조회용 상태. `update_task`으로 설정하지 않는다. 완료 선언 없이 시도가 종료된 작업은 대응 필요 사유를 동반한 pending이 될 수 있다. pending은 자동 재시도의 약속이 아니다. 재개를 위해 다른 ID로 복제하지 않는다.

중단 사유를 해소한 후, 같은 미종료 작업을 명시적으로 재개한다.

```
submit_tasks(batch_id="resume-report", tasks=[{"task_id": "TASK_ID", "resume": true}])
```

저장된 입력을 재사용하고 이력을 유지한다. 운영 중인 시도는 재개할 수 없고, 완료·취소된 작업도 이 방법으로는 재개할 수 없다. 의존 대상이 취소·대응 필요라면 상세를 확인하고, 요청자에게 확인하거나 불필요해진 작업을 취소한다. 성공을 위조하지 않는다.

진행할 수 없을 때는 사실, 시도한 것, 부족한 권한·정보, 다음 수를 요청자에게 전하고, 같은 실패를 반복하지 않는다. 관련 지식 검색은 필요한 경우에만 하고, 의식화하지 않는다. 대기 중에는 다른 허용된 작업에 착수해도 된다. 위임된 일의 완료는 요청자에게 보고하고, 중복 알림이나 불필요한 확인 답변을 피한다.

## 부하에게 위임

```
delegate_task(name="dave", instruction="API テストを実施し検証した結果を報告する", summary="API テスト")
task_tracker()
```

부하가 소유하는 하나의 작업과, 상급자에게 보이는 별칭을 만든다. 양쪽에 같은 최신 상태가 즉시 반영되고, 별도 장부나 Heartbeat 동기화는 불필요. `task_tracker(status="all")`은 종료된 것을 포함하고, `status="completed"`는 done/cancelled을 표시한다. 지침이 불명확하면 위임 원에게 확인하고, 완료 시 결과를 보고한다.

## 작업 맥락과 결과

`state/current_state.md`에는 관찰·맥락·계획·블로커를 간결히 남긴다. 작업 목록의 복제나 영구적인 절차를 두지 않는다. 작업 맥락이 없으면 `status: idle`. 일반적인 세션 경계에서는 유지되고, 표시 제한과 디스크 정리 제한은 별개다(`anatomy/working-memory.md`).

TaskExec의 결과 요약은 `state/task_results/{task_id}/{attempt_token}.md`에 저장된다. 호스트가 수락한 시도의 결과를 후속에 전달하고, 오래된 파일을 임의로 채택하지 않는다. 결과 파일의 위조나 존재만으로 완료를 판단하는 것은 금지. 활동 로그·에피소드는 증적으로 남고, 각 상태 전이를 수동으로 이중 기록할 의무는 없다.

## 장시간 명령 도구는 별도 경로

이미지 생성이나 run_command 등 대응하는 장시간 외부 도구에는 `animaworks-tool submit TOOL ...`를 사용한다. `submit_tasks`의 LLM 작업과 동일한 TaskStore에 `task_type="command"`로 등록되며, BackgroundTaskManager가 실행한다. 실행 시도는 TaskStore에 기록하고, 호환성을 위해 `state/background_tasks/{task_id}.json`와 완료 알림도 유지한다. `list_background_tasks` / `check_background_task`로 결과를 확인한다. 자세한 내용은 `operations/background-tasks.md`.
