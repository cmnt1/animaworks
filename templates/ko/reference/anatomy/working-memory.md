# 작업 메모리 (state/）기술 참조

Anima의 작업 상태를 관리하는 `state/` 디렉터리의 상세 사양.
프롬프트 주입 로직, 크기 제어, 마이그레이션, 잠금 제어를 포함한다.

---

## state/ 디렉터리 구성

```
state/
├── current_state.md          # ワーキングメモリ（自由形式Markdown）
├── task_results/              # TaskExec完了結果
│   └── {task_id}/{attempt_token}.md
├── conversation.json          # 会話状態
├── conversations/             # スレッド別会話ファイル
├── recovery_note.md           # クラッシュ復旧ノート
├── heartbeat_checkpoint.json  # Heartbeatチェックポイント
└── pending_procedures.json    # 保留中の手続き追跡
```

---

## current_state.md

### 역할

Anima의 작업 메모리. "지금 막 무엇을 하고 있는지" "무엇을 관찰했는지" "어떤 블로커가 있는지"를 자유 형식으로 기록한다. 작업 관리용이 아니라 상황 인식을 위한 공간이다.

작업 추적은 호스트 관리의 원본 TaskStore가 담당한다. 확인은 `list_tasks`, 변경은 작업 도구를 사용하며, DB나 큐 파일을 직접 편집하지 않는다.

### 크기 제어

| 파라미터 | 값 | 소스 |
|-----------|-----|-------|
| 표시 상한 | 3000자 | `_CURRENT_STATE_MAX_CHARS`（builder.py） |
| 디스크 trim 상한 | 8000자（기본값） | `heartbeat.current_state_max_chars`（0 = 비활성） |
| Inbox 시 상한 | 500자 | builder.py 내에서 `min(_state_max, 500)` |

**세션 경계**:

- 일반적인 Heartbeat / cron / 대화 최종화에서는 `current_state.md`을 유지한다
- 세션 요약에 현재 상태가 포함되는 경우에도 `current_state.md`가 비어 있거나 idle일 때만 기록한다
- 활성 작업이 없는 오래된 state는 TaskBoard housekeeping에 의해 아카이브될 수 있다. 비표시여도 활성 작업은 state를 보호한다

**Heartbeat 시 임의 정리**:

1. `heartbeat.current_state_max_chars`가 0보다 크고, Heartbeat 시작 전에 `current_state.md`이 그 값을 초과한 경우, "정리하고 압축하라"는 지침이 Heartbeat 프롬프트에 주입된다
2. Heartbeat 또는 cron 완료 후, `_enforce_state_size_limit()`이 실행된다
3. 설정 상한의 초과분은 당일 에피소드 기억(`episodes/{date}.md`)에 `## current_state.md overflow archived`로 이동
4. 끝부분의 설정 문자 수를 유지하고, 줄바꿈 위치에서 조정(앞 20% 이내에 줄바꿈이 있으면 그곳에서 자름)

### 프롬프트로의 주입

| 트리거 | 동작 |
|---------|------|
| `chat` | 전체 주입(3000자 상한, 스케일 적용) |
| `inbox` | 최대 500자로 제한 |
| `heartbeat` / `cron` | 전체 주입(3000자 상한) |
| `task` | **주입하지 않음**(Minimal 티어) |

주입 시, `status: idle`만 있는 경우 섹션 자체가 생략된다.
그 외의 경우 `builder/task_in_progress` 템플릿으로 강조 헤더와 함께 주입된다.

### 잠금 제어

`core/anima/digital_anima.py`의 `_state_file_lock`(`asyncio.Lock`)이 `current_state.md`로의 병행 쓰기를 방지한다.

`_is_state_file(path)`는 `state/current_state.md`에만 `True`을 반환한다. `write_memory_file` 경유의 쓰기에서는 이 파일에 대해 잠금이 자동으로 획득된다.

### 경로 해석(하위 호환)

`read_memory_file` / `write_memory_file`에서 `state/current_task.md`가 지정된 경우, 자동으로 `state/current_state.md`로 해석된다(`handler_memory.py`).

---

## pending.md(폐지됨)

`state/pending.md`은 `current_state.md`에 통합된 후, 자동 삭제된다.

### 마이그레이션(MemoryManager 초기화 시)

1. `state/current_task.md`이 존재하고 `state/current_state.md`이 존재하지 않음 → 이름 변경
2. 둘 다 존재 → `current_state.md`를 우선, 경고 로그
3. `state/pending.md`이 존재하고 내용이 있음 → `current_state.md`에 `## Migrated from pending.md`로 추가 후, 삭제
4. `state/pending.md`이 비어 있음 → 삭제

---

## 이전 작업 파일

`state/task_queue.jsonl`과 `state/pending/`은 마이그레이션·내보내기용 증적으로만 유지한다. 가동 중인 큐가 아니다. 운영자가 이전 쓰기 처리를 중지하고, 백업과 함께 명시적으로 가져온 후 원본 런타임을 시작한다. 재개를 위해 파일을 삭제·재투입·조작하지 않는다.

## 작업 실행과 결과

호스트가 원지시와 작업을 일괄 저장하고, 실행 가능한 작업을 획득하여 각 시도를 기록한다. `in_progress`은 호스트 관리. 에이전트는 `update_task`에서 `done` / `pending` / `cancelled`를 선언한다. `list_tasks(detail=true)`에서 의존 관계와 대응 필요 이유를 확인한다. pending은 재시도를 의미하지 않는다. 원인 해소 후, `submit_tasks(..., tasks=[{"task_id": "ID", "resume": true}])`에서 같은 작업을 명시적으로 재개한다.

수락된 결과 요약은 `state/task_results/{task_id}/{attempt_token}.md`(최대 2000자)에 저장된다. 후속에는 호스트가 선택한 수락된 결과를 전달한다. 오래된 파일의 존재만으로 완료로 판단하지 않는다. 원기록을 보존하고, 결과를 써서 성공한 시도를 가장하지 않는다.

장시간 명령 도구는 별도 경로를 유지한다. `animaworks-tool submit`은 `state/background_tasks/pending/`에 투입하고, BackgroundTaskManager가 명령 상태·알림을 관리한다. 상세는 `operations/background-tasks.md`과 `operations/task-management.md`.

## read_subordinate_state

상급자가 `read_subordinate_state(name="部下名")`을 호출하면, 부하의 `state/current_state.md`만 읽힌다(`pending.md`는 대상 외).
