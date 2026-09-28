# Priming 채널 기술 참조

기본 `compact`는 발신자, 작업, 상주 지식을 획득하고, 조건을 충족하는 경우에만 관련 지식을 검색한다. 옵트인 `full`는 최근 활동과 에피소드도 획득한다. 채널 구성은 `priming.profile`에서 선택되며, 모든 트리거에서 모든 채널이 작동하는 것은 아니다.

`PrimingEngine`가 획득하는 채널과 예산의 사양을 보여준다. C0(important_knowledge)는 Channel C의 지식 파이프라인 내 보조 블록이다.

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

**Priming 주입과 명시적 검색의 차이**: Channel B는 `full` 프로필로 획득한다. 과거 행동 로그를 키워드로 넓게 찾는 용도는 `search_memory(scope="activity_log")`를 사용한다. 주입과 도구 검색은 별도의 경로이다.

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

## 예산과 프로필

`config.json`의 `priming.profile`은 `compact` 또는 `full`을 지정한다(기본값: `compact`). Anima별 `status.json`에 `priming_profile`을 지정하면 해당 설정이 우선된다. `priming.max_tokens`은 회상의 토큰 예산(기본값: 2000), `priming.channel_timeout_seconds`은 채널별 획득 타임아웃(기본값: 60초).

- `compact`는 A(발신자), E(작업), C0(상주 지식), 최근 전송, 보류 중인 인간 알림을 획득한다. C(관련 지식)는 chat/task 트리거, 또는 question/request/delegation 의도가 있고 메시지가 있는 경우에 획득한다. B(최근 활동)·F(에피소드)·G(병렬 작업 표시)는 획득하지 않는다.
- `full`는 A / B / C0 / C / E / F와 최근 전송, 인간 알림을 획득한다.
- A의 상한은 `min(400, max_tokens // 4)`, E의 상한은 `min(500, max_tokens // 3)`. 최근 전송은 최대 3건·250토큰. `full`의 채널 항목과 `compact`의 관련 지식은 `max_tokens`의 남은 범위에 맞춘다.
- 보류 중인 인간 알림은 회상 예산과 별도로 취급된다.

---

## Hebbian LTP(장기 강화)

Priming에서 검색·표시된 청크는 `record_access(kind="retrieved")`에 의해 가벼운 검색 기록이 업데이트된다. `read_memory_file`이나 outcome 보고에 의한 명시적 사용은 `used`로 기록되며, 망각 보호는 이 명시적 사용을 기준으로 한다.
