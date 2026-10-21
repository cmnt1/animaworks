<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/inbox-task-submission.md -->
<!-- i18n: source-sha256=80ab667f58d4c9d8b5d2766739d2c5ea1c83000ca891481342a035bb236bb81e generated=2026-10-21 engine=nanogpt model=deepseek/deepseek-v4.1-flash translator=2 -->

# Inbox에서 받은 의뢰를 실행 작업에 연결하기

## 대상과 전제

Discord 등에서 Inbox로 도착하는, 사용자가 허용한 조사·검증·작업이 대상이다.
`inbox` 과 `inbox:<sender>` 은 `submit_tasks` 을 공개한다.
TaskExec (`task:*`)·일반 채팅·cron·기억 통합에서는 공개하지 않는다.
TaskExec에서의 하위 작업 생성 금지도 유지한다.

## Anima가 수행하는 절차

1. 의뢰 원문과 필요한 기록을 읽고, `list_tasks(detail=true)` 으로 기존 작업을 확인한다.
   목록이 비어 있어도 과거 검증이 미실시라는 뜻은 아니다. 완료된 산출물도 확인한다.
2. 응답 내에서 끝나는 작업은 직접 실행한다. 계속이 필요한 허용된 작업은,
   `submit_tasks` 에 고유한 `batch_id` 와 `tasks` 을 전달하여 실행 가능한 작업으로 만든다.
   `current_state.md` 의 메모나 추적용 대장 등록만으로 끝내지 않는다.
3. 작업에는 원문, 목적, 입력·기존 산출물, 첫 산출물, 완료 조건,
   제약, 최초 보고 마감일, 보고 대상을 포함한다. 사양이 미확정이면 자료 조사,
   명시한 가정, 감도 분석 설계부터 진행하고, 가정을 실운용의 확정 규칙과 혼동하지 않는다.
4. `status: submitted` 와 `task_ids` 을 확인한 후 접수 보고한다.
   ID·담당·첫 산출물·최초 보고 마감일을 제시하고, 시작 미확인이면 "등록됨·실행 대기"라고 쓴다.
   등록 실패 시 실제 오류를 보고한다. 사용할 수 있는 도구를 시도하지 않고 "등록할 수 없다"고 단정하지 않는다.
5. 기존의 미완료 작업은 중복 등록하지 않는다. 중지 이유가 해소된 경우에만,
   같은 `task_id` 과 `resume:true` 으로 재개한다. 이미 완료된 분석에 추가 검증을
   의뢰받은 경우에는, 이전 산출물과 ID를 참조하는 후속 작업을 만든다.
6. 원래 스레드에 결과 또는 블로커를 보고한다. Inbox의 최종 응답은 자동 회신되므로,
   같은 접수 문구를 전송 도구로 이중 게시하지 않는다. TaskExec의 후속 보고 대상은 작업 본문에 명시한다.

## 운용자의 검증 절차

- 도구 공개 회귀 확인:
  `.venv/Scripts/python.exe -m pytest tests/unit/core/tooling/test_submit_tasks_trigger_gate.py tests/unit/core/tooling/test_tool_surface_matrix.py tests/unit/core/test_mcp_server.py tests/unit/execution/test_sdk_hooks_agent_intercept.py tests/unit/core/test_submit_drain_integration.py -q`
- 기존 Anima 프로세스가 구 모듈을 보유하고 있는 경우, 가동 중인 작업이 없음을 확인한 후
  `POST /api/animas/<name>/restart` 로 대상 Anima만 재시작한다.
  서버 전체 재시작은 불필요하다.
- 명시적으로 허용된 의뢰를 Inbox에 전달하고, activity_log에서 본인의 `submit_tasks` 호출과
  `status: submitted` 을 확인한다. 운용자가 대행 등록한 작업으로는 본인의 등록 능력 확인이 되지 않는다.
- `animaworks task show <id> --json` 에서 attempt의 `started_at` 을 확인한다.
  `in_progress`, 산출물, 후속 보고를 각각 확인하고, 등록 성공과 검증 완료를 혼동하지 않는다.
- `state/task_queue.jsonl` 이나 `state/pending/` 은 구 마이그레이션 증적이다. 직접 편집·재투입하지 않는다.

## 2026-10-21의 원인

rika의 행동 규칙은 등록을 요구한 반면, 공유 도구 정책은 Inbox에서
`submit_tasks` 을 제외했고, Inbox 공통 프롬프트도 사용을 금지하고 있었다.
도구 공개와 일본어·영어·한국어 공통 프롬프트를 맞추어 수정했다.
CLI의 우회 실행을 일반 절차로 삼지 않고, 정식 도구로 등록한다.

실기 확인에서는 운용자가 rika의 Inbox에 의뢰 원문을 전달하고, 본인의
`submit_tasks` 호출과 `status: submitted` 을 2026-10-21 12:23:09 JST에 확인했다.
후속 ID는 `rotation-followup-20261021`, batch는 `rika-rotation-20261021`.
task show에서도 최초 attempt의 시작을 확인 완료했다. 이전의 운용자에 의한 대행 등록과 달리,
이번에는 Inbox 응답을 담당하는 rika 자신이 등록했다. Discord의 새로운 Gateway 이벤트를
위장하지 않고, 같은 Inbox 처리계에 대한 운용자 메시지로 확인했다.
최초 보고 마감일은 등록으로부터 60분 이내(13:23 JST). 이 ID는 실제 검증 준비 작업이므로,
동작 확인을 위해 같은 작업을 재등록하지 않는다.
