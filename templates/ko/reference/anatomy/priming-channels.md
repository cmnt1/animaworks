# Priming 채널 기술 참조

Priming은 compact 단일 경로로 작동한다. 발신자·작업·상주 지식·최근 전송·사람을 위한 알림을 가져오며, 조건을 충족하는 경우 관련 지식도 검색한다. heartbeat / inbox / cron에서는 공통 상한 설정에 따라 최근 활동이나 에피소드도 가져온다.

`PrimingEngine`가 가져오는 채널과 예산 사양을 보여 준다. C0(important_knowledge)는 Channel C의 지식 파이프라인 내 보조 블록이다.

## 채널 목록

| 채널 | 소스 | trust |
|---------|--------|-------|
| A: sender_profile | `shared/users/{sender}/index.md` | medium |
| B: recent_activity | `activity_log/` + 공유 채널 | trusted |
| C: related_knowledge | RAG 벡터 검색(knowledge + common_knowledge) | medium / untrusted |
| C0: important_knowledge | `[IMPORTANT]` 태그가 붙은 청크 | medium |
| E: pending_tasks | TaskStore + task results | trusted |
| F: episodes | RAG 벡터 검색(episodes/） | medium |

추가 주입:

| 항목 | 소스 | trust |
|------|--------|-------|
| Recent outbound | activity_log(최대 3건, `channel_post` / `message_sent`) | trusted |
| Pending human notifications | `human_notify` 이벤트 | trusted |

스킬·절차의 본문은 Priming에서 주입되지 않는다. 시스템 프롬프트의 스킬 카탈로그에 표시된 경로(예: `skills/foo/SKILL.md`, `common_skills/bar/SKILL.md`, `procedures/baz.md`)를 `read_memory_file`로 읽어들인다.

---

## Channel A: sender_profile

발신자의 사용자 프로필을 주입한다.

- **소스**: `shared/users/{sender}/index.md`을 직접 읽기
- **상한**: `min(400, max_tokens // 4)`
- **발신자 불명 시**: 건너뜀

---

## Channel B: recent_activity

최근 활동 타임라인을 주입한다.

- **소스**: `activity_log/{date}.jsonl` + 공유 채널의 최신 게시물

**Priming 주입과 명시적 검색의 차이**: Channel B는 heartbeat / inbox / cron의 compact한 배경 회상으로, 공통 설정의 상한 내에서 가져온다. 과거 행동 로그를 키워드로 폭넓게 찾으려면 `search_memory(scope="activity_log")`을 사용한다. 주입과 도구 검색은 별개의 경로다.

### 트리거별 필터링

| 트리거 | 제외되는 이벤트 유형 |
|---------|----------------------|
| `heartbeat` / `cron` / `inbox` / `task` | `tool_use`, `tool_result`, `heartbeat_start`, `heartbeat_reflection`, `inbox_processing_start`, `inbox_processing_end` |
| 기타 | `tool_use`, `tool_result`, `memory_write`, `cron_executed`, `heartbeat_start`, `heartbeat_end`, `heartbeat_reflection`, `inbox_processing_start`, `inbox_processing_end` |

---

## Channel C: related_knowledge

RAG 벡터 검색으로 관련 지식을 주입한다.

- **검색 방식**: Dual-query(메시지 컨텍스트 + 키워드만)
- **검색 대상**: 개인 `knowledge/` + `shared_common_knowledge` 컬렉션
- **최소 점수**: `config.json`의 `rag.min_retrieval_score`(기본값 0.3)

### trust 분리

검색 결과는 청크의 `origin`에 기반하여 trust 수준으로 분리된다:

| trust | 대상 | 처리 |
|-------|------|------|
| `medium` | 개인 knowledge, common_knowledge | 우선적으로 예산을 소비 |
| `untrusted` | 외부 플랫폼 유래(`origin_chain`에 `external_platform` 포함) | 남은 예산으로 주입. `origin=ORIGIN_EXTERNAL_PLATFORM` 태그가 붙음 |

---

## Channel C0: important_knowledge

`[IMPORTANT]` 태그가 붙은 청크의 개요 포인터를 주입한다.

- **대상**: `knowledge/` 내의 `[IMPORTANT]` 태그가 붙은 청크
- **주입 형식**: 개요 포인터. 상세는 `read_memory_file`로 획득
- **용도**: 중요한 업무 규칙·판단 기준의 회상

---

## Channel E: pending_tasks

작업 큐의 요약을 주입한다.

- **상한**: `min(500, max_tokens // 3)`
- **소스**: `TaskQueueManager.format_for_priming()`
- **내용**:
  - `pending` / `in_progress` 작업의 목록과 요약
  - 인간이 기재한 작업에 🔴 HIGH 마커
  - 30분 이상 업데이트가 없는 작업에 ⚠️ STALE 마커
  - 위임 작업의 상태
  - `task_results/`에서의 완료 작업 결과

---

## Channel F: episodes

RAG 벡터 검색으로 관련 에피소드를 주입한다.

- **검색 대상**: `episodes/` 컬렉션
- **최소 점수**: Channel C와 공통(`rag.min_retrieval_score`)

---

## 예산 및 설정

프로필 선택은 없으며, Priming은 항상 compact 가져오기 경로를 사용한다. `priming.max_tokens`은 회상 예산(기본값: 2000), `priming.channel_timeout_seconds`은 채널별 가져오기 시간 제한(기본값: 60초)이다. `compact_background_recall`는 heartbeat / inbox / cron에서 공유하는 하나의 상한 집합이며, `compact_background_recall_enabled`으로 한꺼번에 비활성화할 수 있다.

- A(발신자)는 `min(400, max_tokens // 4)`, E(작업)는 `min(500, max_tokens // 3)`가 상한이다. 최근 전송은 최대 3건·250토큰이다.
- C(관련 지식)는 chat/task 트리거 또는 question/request/delegation 의도가 있고, 메시지가 있는 경우 가져온다.
- B(최근 활동)는 heartbeat / inbox / cron에서 설정 상한 내로 가져온다. F(에피소드)는 동일한 트리거로 메시지가 있고 관련 가져오기가 활성화된 경우 설정 상한 내에서 가져온다.
- 보류 중인 사람 알림은 회상 예산과 별도로 처리된다.

---

## Hebbian LTP(장기 강화)

Priming에서 검색·표시된 청크는 `record_access(kind="retrieved")`에 의해 가벼운 검색 기록이 업데이트된다. `read_memory_file`이나 outcome 보고에 의한 명시적 사용은 `used`로 기록되며, 망각 보호는 이 명시적 사용을 기준으로 한다.
