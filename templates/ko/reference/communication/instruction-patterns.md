# 지시 패턴 모음

부하나 팀원에게 명확하고 실행 가능한 지시를 내리기 위한 패턴 모음입니다.
모호한 지시는 재작업과 혼란의 원인이 됩니다. 이 가이드에 따라 상대방이 망설이지 않고 행동할 수 있는 지시를 작성하세요.

## 도구 선택

| 도구 | 용도 | 비고 |
|------|------|------|
| `delegate_task` | 배하에게 태스크 위임 | 태스크 큐에 추가 + DM 전송. 진행 상황을 `task_tracker`로 추적 가능. 자식, 손자 등 모든 배하에 사용 가능 |
| `send_message` | 1:1 의뢰, 보고, 질문 | `intent` 필수: `report` / `question` 중 하나. 배하에게 태스크 위임 시 `delegate_task` 사용. 사람 별명은 외부 channel (Slack, Chatwork 등)로 전달 |
| `post_channel` | 전체 공유 (공지, 해결 보고) | 확인, 감사, FYI는 Board 사용. `@이름`으로 멘션 (멘션 대상에게 DM 통지). 상세는 `board-guide.md` 참조 |
| `manage_channel` | Channel ACL 관리 | Channel 생성, 멤버 추가/삭제, 정보 확인. 제한 channel 운영 시 사용. 상세는 `board-guide.md` 참조 |

**send_message 제약**:
- `intent` 필수. `report` / `question`만 허용. 배하에게 태스크 위임은 `delegate_task` 사용. 확인/감사/FYI는 Board (`post_channel`) 사용
- 1 run당 최대 N 수신자, 각 수신자 1통까지. N은 역할별 기본값 (general=2, ops=2, writer=3, researcher=3, engineer=5, manager=10). `status.json`의 `max_recipients_per_run`으로 오버라이드 가능. N명 이상에게 전달 시 Board 사용
- 선택 사항: `thread_id` (스레드 ID), `reply_to` (답장 대상 메시지 ID)로 대화 스레드 유지 가능

**post_channel 제약**:
- Channel 멤버여야 함 (ACL). 제한 channel의 경우 비멤버는 게시 불가
- 동일 run 내 같은 channel에 1회만 게시 가능
- 동일 channel 재게시 시 쿨다운 필요 (`config.json`의 `heartbeat.channel_post_cooldown_s`, 기본 300초. 0으로 비활성화)
- DM과 Board는 동일한 아웃바운드 예산을 공유 (`max_outbound_per_hour` / `max_outbound_per_day`). 시간/일별 상한에 도달하면 게시가 차단됨

## 명확한 지시의 5요소

지시를 내릴 때 다음 5가지 요소를 포함하세요 (MUST). 상대방의 확인 및 재작업을 최소화합니다.

| 요소 | 설명 | MUST/SHOULD |
|------|------|-------------|
| 목적 (왜) | 이 작업이 필요한 이유와 배경 | MUST |
| 기대 성과 (무엇을) | 완료 시 무엇이 만들어지는가 | MUST |
| 기한 (언제까지) | 작업 완료 기한 | MUST (급하지 않아도 대략적 목표 제시) |
| 제약/조건 (어떻게) | 사용할 방법, 피해야 할 것 | SHOULD |
| 보고 시점 (언제 보고) | 완료 시 / 중간 경과 / 문제 발생 시 | MUST |

## 좋은 지시 vs 나쁜 지시

### 예시 1: 데이터 집계 의뢰

**나쁜 지시:**
```
send_message(
    to="alice",
    content="매출 데이터 집계해 주세요.",
    intent="question"
)
```
문제점: 어떤 데이터인지, 어느 기간인지, 어떤 형식으로 출력하는지, 기한이 불명확. 배하에게 의뢰라면 `delegate_task` 사용.

**좋은 지시:** (배하라면 `delegate_task` 사용. 동료/비배하 의뢰는 `intent="question"`)
```
send_message(
    to="alice",
    content="""매출 데이터 월간 집계를 부탁합니다.

목적: 경영 회의 (2/20) 자료
대상: 2026년 1월 매출 데이터 (/shared/data/sales_202601.csv)
산출물: 부서별/제품 카테고리별 집계표 (Markdown 형식)
출력 위치: /shared/reports/sales_summary_202601.md
기한: 2/18 (화) 17:00까지
보고: 완료 시 결과 요약을 답장해 주세요.""",
    intent="question"
)
```

### 예시 2: 조사 태스크 의뢰

**나쁜 지시:**
```
send_message(
    to="bob",
    content="API 오류 좀 조사해 줘.",
    intent="question"
)
```
문제점: 어떤 API, 어떤 오류, 조사 깊이, 보고 형식이 불명확. 배하라면 `delegate_task` 사용.

**좋은 지시:**
```
send_message(
    to="bob",
    content="""GitHub API 레이트 제한 오류 (HTTP 403) 조사를 부탁합니다.

배경: 어제 15시경부터 간헐적으로 발생, 자동 배포 실패 중
조사 항목:
1. 오류 발생 빈도와 패턴 (로그: /var/log/deploy/github-api.log)
2. 현재 레이트 제한 설정 및 사용 상황
3. 회피 방안 제안 (재시도 전략, 토큰 분산 등)

기한: 오늘 중
보고: 조사 결과와 권장 대책을 정리하여 답장해 주세요.
중간에 중대한 발견이 있으면 즉시 보고해 주세요.""",
    intent="question"
)
```

### 예시 3: 리뷰 의뢰

**나쁜 지시:**
```
send_message(
    to="carol",
    content="코드 좀 봐줘.",
    intent="question"
)
```

**좋은 지시:** (carol이 배하이면 `delegate_task` 사용. 동료/비배하 의뢰는 intent="question")
```
send_message(
    to="carol",
    content="""인증 모듈 코드 리뷰를 부탁합니다.

대상 파일: ~/project/auth/token_manager.py (신규 추가)
확인 관점:
- 보안 우려사항 (토큰 저장, 무효화 처리)
- 오류 처리 커버리지
- 기존 auth_handler.py와의 정합성

기한: 내일 (2/16) 오전 중
보고: 문제 없으면 "LGTM", 수정이 필요하면 구체적인 위치와 이유를 답장해 주세요.""",
    intent="question"
)
```

## 태스크 위임 패턴

### 패턴 1: 단발 태스크 (배하에게 위임)

1회성 작업을 **배하** (자식, 손자 등)에게 위임하는 경우 `delegate_task`를 사용합니다. 태스크 큐에 추가되어 진행 상황을 `task_tracker`로 추적할 수 있습니다.

필수 파라미터: `name` (위임 대상), `instruction` (지시 내용), `deadline` (상대 형식 `30m`/`2h`/`1d` 또는 ISO8601). 선택: `summary` (1줄 요약).

```
delegate_task(
    name="alice",
    instruction="""API 사양서 (/shared/docs/api-spec.md)에 v2.1 변경 사항을 반영해 주세요.

변경 내용:
- /api/users 엔드포인트에 페이지네이션 파라미터 추가
- 응답에 total_count 필드 추가
- 변경 상세: /shared/docs/changelog-v2.1.md 참조

완료되면 답장 부탁합니다.""",
    deadline="2d",
    summary="API 사양서 v2.1 반영"
)
```

### 패턴 1b: 단발 태스크 (동료/비배하에게 의뢰)

배하가 아닌 상대에게 의뢰할 때는 `send_message`에 `intent="question"`을 지정합니다.

```
send_message(
    to="alice",
    content="""[의뢰] 문서 업데이트

API 사양서 (/shared/docs/api-spec.md)에 v2.1 변경 사항을 반영해 주세요.

변경 내용:
- /api/users 엔드포인트에 페이지네이션 파라미터 추가
- 응답에 total_count 필드 추가
- 변경 상세: /shared/docs/changelog-v2.1.md 참조

기한: 2/16 15:00
완료되면 답장 부탁합니다.""",
    intent="question"
)
```

### 패턴 2: 계속 태스크 (정기 작업 위임)

Heartbeat이나 cron에 포함시켜야 할 정기 태스크를 지시하는 패턴입니다. 계속 태스크는 `delegate_task` 대상이 아니므로 `send_message`에 `intent="question"`을 지정합니다.

```
send_message(
    to="bob",
    content="""[계속 의뢰] 일일 로그 모니터링

앞으로 매일 오전에 애플리케이션 로그 이상 체크를 수행해 주세요.

대상: /var/log/app/error.log
확인 내용:
- 최근 24시간 ERROR/CRITICAL 레벨 로그 건수
- 새로운 패턴의 오류가 있는지

보고 규칙:
- 이상 없음 → 보고 불필요
- ERROR 10건 이상 또는 신규 패턴 → 즉시 나에게 보고
- 매주 금요일에 1주간 요약 보고

이 내용을 본인의 heartbeat 체크리스트에 추가해 주세요.""",
    intent="question"
)
```

### 패턴 3: 단계적 태스크 (마일스톤 포함)

큰 태스크를 단계별로 위임하는 패턴입니다. 배하라면 `delegate_task` 사용. 동료/비배하 의뢰는 `intent="question"`.

```
send_message(
    to="carol",
    content="""[의뢰] 새 기능 설계 및 구현 (3단계)

사용자 알림 기능 추가를 부탁합니다.

Phase 1 (2/17까지): 설계
- 알림 유형 (이메일/Slack/인앱)과 우선순위 정의
- 데이터 모델 설계안
→ 설계안을 답장해 주세요. 제가 승인 후 Phase 2로 진행하세요.

Phase 2 (2/20까지): 구현
- 승인된 설계에 기반하여 구현
- 테스트 코드 포함
→ 완료되면 답장해 주세요.

Phase 3 (2/21까지): 문서
- API 사양서와 사용 가이드 작성

각 Phase 완료 시 답장 부탁합니다.
Phase 간 방향이 불확실하면 상담해 주세요.""",
    intent="question"
)
```

## 후속 조치 (진행 확인) 패턴

### 기한 전 확인

진행 확인은 질문이므로 `intent="question"`을 지정합니다.

```
send_message(
    to="alice",
    content="""매출 데이터 집계 진행 상황을 확인합니다.
기한은 내일 (2/18) 17:00인데, 순조롭게 진행 중인가요?
차단 요소가 있으면 알려 주세요.""",
    intent="question"
)
```

### 기한 초과 후 후속 조치

```
send_message(
    to="bob",
    content="""로그 모니터링 조사 결과에 대해 확인합니다.
오늘이 기한이었는데, 상황이 어떤가요?
어려운 점이 있으면 알려 주세요. 필요하면 기한을 연장합니다.""",
    intent="question"
)
```

### 산출물 수령 후 피드백

수정 의뢰는 위임에 해당하므로 배하라면 `delegate_task` 사용. 동료/비배하 의뢰는 `intent="question"` 지정.

```
send_message(
    to="carol",
    content="""설계안을 확인했습니다. 전체적으로 좋은 방향입니다.

수정 요청 사항:
1. 알림 재전송 로직에 지수 백오프를 추가해 주세요
2. 알림 템플릿의 i18n 대응을 설계에 포함해 주세요

위 내용을 반영한 수정본을 2/18까지 부탁합니다.""",
    intent="question"
)
```

## 에스컬레이션 판단 기준

직접 처리할지, 상사에게 에스컬레이션할지의 판단 기준입니다.

### 직접 처리할 경우 (에스컬레이션 불필요)

- 절차가 명확하고 자신의 권한 범위 내에서 완결되는 작업
- 경미한 오류로 기존 복구 절차가 있는 경우
- 부하의 질문에 자신의 지식으로 답변 가능한 경우
- 우선순위가 명확하고 판단에 고민이 없는 경우

### 에스컬레이션할 경우

- MUST: 자신의 권한을 넘는 판단이 필요한 경우 (예: 외부 API 연동 방침 변경)
- MUST: 여러 부서에 영향을 미치는 인시던트가 발생한 경우
- MUST: 기한에 못 맞추는 것이 확실해진 경우
- SHOULD: 예상 밖의 상황에서 정답이 여러 개이고 판단이 어려운 경우
- SHOULD: 부하로부터의 에스컬레이션에서 자신도 해결하지 못하는 경우

### 에스컬레이션 전달법

에스컬레이션은 상사에게의 보고 및 판단 요청이므로 `intent="report"`를 지정합니다. 긴급 시에는 `call_human`도 검토하세요.

상사가 Anima인 경우 `to`에 Anima 이름을 지정. 사람 관리자에게 보내는 경우 `config.json`의 `external_messaging.user_aliases`에 설정한 별명을 `to`에 지정하면 Slack/Chatwork 등 외부 channel로 자동 전달됩니다.

```
send_message(
    to="manager",
    content="""[에스컬레이션] 배포 파이프라인 장애

상황: GitHub API 레이트 제한으로 자동 배포가 12시간 중단 중
영향: 오늘 릴리스 예정 기능 (v2.1) 배포 불가
시도한 대책: 재시도 간격 연장, 캐시 활용 (모두 효과 없음)
판단이 필요한 점: 별도 GitHub 토큰 발급 또는 수동 배포 전환

판단을 부탁합니다.""",
    intent="report"
)
```

## 지시 템플릿

다음 템플릿을 `send_message`로 사용할 때 `intent`를 적절히 지정하세요 (의뢰=question, 보고=report, 질문=question. 배하에게 태스크 위임은 `delegate_task` 사용).

### 범용 태스크 의뢰 템플릿

```
[의뢰] {태스크명}

{배경 및 목적 (1-2줄)}

작업 내용:
- {구체적인 작업 1}
- {구체적인 작업 2}

산출물: {무엇을 어디에 출력하는지}
기한: {일시}
보고: {완료 시/중간 경과/문제 발생 시 중 하나}
```

### 조사 의뢰 템플릿

```
[조사 의뢰] {조사 주제}

배경: {이 조사가 필요한 이유}

조사 항목:
1. {조사 항목 1}
2. {조사 항목 2}
3. {조사 항목 3}

기한: {일시}
보고: 조사 결과와 권장 조치를 정리하여 답장해 주세요.
```

### 리뷰 의뢰 템플릿

```
[리뷰 의뢰] {대상명}

대상: {파일 경로 또는 리소스}
확인 관점:
- {관점 1}
- {관점 2}

기한: {일시}
보고: 문제 없으면 "LGTM", 수정이 필요하면 구체적으로 답장해 주세요.
```
