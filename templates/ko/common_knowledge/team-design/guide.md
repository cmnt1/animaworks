# 팀 설계 가이드 — 기본 원칙

## 개요

이 문서는 목적별로 Anima 팀을 설계할 때의 기본 원칙을 정의한다.
프레임워크의 조직 메커니즘(`organization/roles.md`, `organization/hierarchy-rules.md`)과는 별도로,
**「어떤 목표에 대해 어떤 역할 구성으로 팀을 짤 것인가」**를 설계하기 위한 가이드이다.

---

## 왜 기능을 나누는가

AI 에이전트에서 역할 분리는 인간 팀과 다른 이유가 있다:

| 이유 | 설명 |
|------|------|
| **컨텍스트 오염 방지** | 한 에이전트가 전 과정을 맡으면 컨텍스트 윈도우가 비대해지고 판단이 나빠진다. 역할로 범위를 한정한다. |
| **전문성 심화** | 역할별 지침·체크리스트·기억을 두면 범용 에이전트보다 품질을 높일 수 있다. |
| **병렬 실행** | 독립된 관점의 역할(예: 리뷰와 테스트)은 동시에 돌려 처리량을 올릴 수 있다. |
| **품질의 구조적 보장** | 「실행」과 「검증」을 나누면 셀프 리뷰의 사각을 줄인다. |

---

## 설계 원칙

### 1. 단일 책임(Single Responsibility)

한 역할에는 하나의 명확한 책무를 둔다. 모호한 역할은 판단 기준이 불명확해져 품질이 떨어진다.

**좋은 예**: 「코드 리뷰 수행 및 품질 판정」(Reviewer)  
**나쁜 예**: 「구현과 리뷰와 테스트」(올인원)

### 2. 실행과 검증의 분리

machine이 실행한 출력을 **같은 Anima가 검증**하는 구조로 둔다. machine 출력을 검증 없이 다음 단계로 넘기지 않는다.

```
Anima가 지시서 작성 → machine 실행 → Anima가 검증·승인
```

### 3. 문서 기반 핸드오프

역할 간 인계는 상태가 있는 Markdown으로 한다. 메시지 본문만으로 넘기면 정보가 빠진다.

```
plan.md (status: approved) → delegate_task로 Engineer에게
```

### 4. 병렬 실행 가능 설계

독립된 역할은 병렬로 돌릴 수 있게 설계한다. 의존이 없는 역할을 불필요하게 직렬로 두지 않는다.

---

## 팀 설계 프로세스

### 1단계: 목표 정의

팀이 달성해야 할 목표를 한 문장으로 명확히 한다.

예:
- 「계획부터 구현·검증까지 소프트웨어 개발 프로젝트를 일관되게 수행한다」
- 「고객 지원 1차 대응을 24시간 한다」

### 2단계: 역할 분해

필요한 기능을 나열하고 단일 책임에 따라 역할로 쪼갠다.

판단 기준:
- **판단이 필요한가** → 독립 역할 가치가 있음
- **다른 작업과 독립적으로 실행 가능한가** → 분리해 병렬 이점을 취함
- **전문 지식이 필요한가** → 전문 역할로 품질을 올림

### 3단계: 책임 경계 명확화

각 역할의 MUST / SHOULD / MAY를 정의한다. 특히 인접 역할 간 경계를 명확히 한다.

### 4단계: 핸드오프 체인 설계

문서 전달 순서와 병렬 실행 지점을 정한다.

### 5단계: 역할 템플릿 선택

프레임워크 `--role`(engineer, manager, writer, researcher, ops, administration) 중 가장 가까운 것을 고르고,
`injection.md`에서 팀 설계로 덮어쓴다.

---

## 겸임 판단

소규모 팀이나 리소스 제약이 있으면 한 Anima가 여러 역할을 겸할 수 있다.

### 겸임해도 되는 경우

- **태스크 규모가 작음** — 한 사람이 전 과정을 돌려도 품질 유지 가능
- **관점이 가까움** — 예: PdM + Engineer(소규모 변경에서 계획·구현이 밀접)
- **비용** — 전용 Anima를 둘 만큼의 작업량이 없음

### 분리하는 편이 좋은 경우

- **실행과 검증이 동일 인물** — Engineer가 자기 코드를 리뷰하는 상태는 피함
- **컨텍스트 충돌** — 리뷰 관점과 구현 관점 전환이 잦음
- **병렬 이득이 큼** — 리뷰와 테스트를 동시에 돌리고 싶음

### 겸임 시

**역할 전환을 의식**한다. 「지금은 Reviewer로 판단」「지금은 Engineer로 구현」을 구분한다.

---

## 규모 스케일링

| 규모 | 구성 | 적용 시나리오 |
|------|------|---------------|
| **솔로** | 1 Anima가 전 역할 겸임 | 소규모 태스크, 프로토타입 |
| **페어** | PdM + Engineer(리뷰는 Engineer 겸임) | 중형 정형 태스크 |
| **풀 팀** | PdM + Engineer + Reviewer + Tester | 본격 프로젝트 |
| **스케일** | PdM + Engineer 여러 명 + Reviewer/Tester 1~2명씩 | 대규모·다중 모듈 |

스케일업 판단:
- 실패 비용이 크다 → 역할 분리 증가
- 병렬 가능한 모듈이 많다 → Engineer 증가
- 품질 요구가 높다 → Reviewer·Tester 독립

---

## 팀 템플릿 목록

| 템플릿 | 경로 | 개요 |
|--------|------|------|
| 개발 풀 팀 | `team-design/development/team.md` | PdM + Engineer + Reviewer + Tester 4역할 |
| 법무 풀 팀 | `team-design/legal/team.md` | Legal Director + Legal Verifier + Precedent Researcher 3역할 |
| 재무 풀 팀 | `team-design/finance/team.md` | Finance Director + Financial Auditor + Data Analyst + Market Data Collector 4역할 |
| 트레이딩 풀 팀 | `team-design/trading/team.md` | Strategy Director + Market Analyst + Trading Engineer + Risk Auditor 4역할 |
| 영업·마케팅 풀 팀 | `team-design/sales-marketing/team.md` | Director + Marketing Creator + SDR + Market Researcher 4역할 |
| 비서(사람 직속) | `team-design/secretary/team.md` | Secretary 1역할(team-of-one). 정보 트리아지·대행 전송·문서 작성(machine) |
| COO(사업 총괄·사람 직속) | `team-design/coo/team.md` | COO 1역할(team-of-one). 위임 판단·부문 감시·KPI 집계·경영 보고(machine) |
| CS(고객 성공) 풀 팀 | `team-design/customer-success/team.md` | CS Lead + Support 2역할. 온보딩·헬스 분석·리텐션·VoC 집약(4페이즈 machine 활용) |
| 경영기획 풀 팀 | `team-design/corporate-planning/team.md` | Corporate Strategist + Business Analyst + Strategy Coordinator 3역할. 전략 수립·사업 분석(machine)·독립 검증(메타 검증)·Strategic Initiative Tracker |
| 인프라/SRE 모니터링 팀 | `team-design/infrastructure/team.md` | Infra Director + Monitor 2역할. 모니터링 팀 패턴(machine 미사용)·보고 템플릿 3종·3단계 에스컬레이션 |
| 조직도 템플릿 | `team-design/org-chart-template.md` | 권장 조직 계층·부문 배치·핸드오프 맵·단계적 도입 가이드 |

> 새 템플릿을 추가할 때는 같은 구조(`team.md` + 역할별 디렉터리)로 `team-design/{팀 이름}/`에 둔다.

---

## 모니터링 팀 패턴

machine(외부 에이전트)을 활용하지 않는 팀을 위한 설계 패턴.
로컬 모델이나 경량 모델(`ops` 역할)로 운용하는 것을 전제로 한다.

### 풀 팀 패턴과의 차이

| 관점 | 풀 팀 패턴 | 모니터링 팀 패턴 |
|------|-----------|----------------|
| 품질 보증의 주축 | machine 출력 검증 | 체크리스트 + 보고 템플릿 |
| 핸드오프 | 문서 상태(reviewed → approved) | 보고 템플릿(정기·이상·집약) |
| 병렬 실행 | 역할 간 독립(예: Reviewer와 Tester) | Monitor 간 독립(모니터링 대상별) |
| Tracker | 도메인 고유 Tracker(silent drop 방지) | 보고 템플릿의 「이전 미해결 항목」으로 대체 |
| cron/heartbeat | 보조적(정기 리뷰 등) | **주전장**(정기 모니터링 점검이 업무의 핵심) |
| 모델 요건 | 추론력 필요(검증·판단) | 규칙 기반 판정이 주체(경량 모델로 충분) |

### 설계 원칙

1. **cron/heartbeat가 주전장**: 모니터링 항목의 정기 실행이 팀의 주요 업무. cron 설정의 품질이 팀의 품질을 결정
2. **보고 템플릿으로 품질 보증**: machine 출력 검증이 아닌 표준화된 보고 포맷으로 구조적으로 품질을 보증
3. **파라미터화로 복수 인스턴스 대응**: Monitor 템플릿을 `{모니터링 대상}`, `{모니터링 항목 테이블}`, `{에스컬레이션 임계값}`으로 파라미터화하여 동일 템플릿에서 복수 Monitor 생성
4. **3단계 에스컬레이션**: INFO / WARNING / CRITICAL 3단계로 대응 수준을 구조화
5. **silent drop 방지는 보고로 담보**: 독립 Tracker가 아닌 보고 템플릿의 「이전 미해결 항목」 섹션에서 미해결 항목을 이월

### 적용 장면

- 인프라/SRE 모니터링 팀
- 정기적인 점검·보고가 주된 업무인 팀
- 경량 모델 운용이 바람직한 팀

---

## team-of-one 패턴: 사람 직속 변형

비서 템플릿과 COO 템플릿은 team-of-one 패턴의 특수 변형으로, **상위자가 사람**이라는 점이 다른 모든 템플릿과 근본적으로 다르다.

### 일반 팀 템플릿과의 차이

| 관점 | 일반 템플릿 | team-of-one(사람 직속) |
|------|-----------|----------------------|
| 상위자 | Anima(supervisor 필드) | 사람(`supervisor: null`) |
| 상위 보고 | `send_message`(intent: report) | `call_human` |
| 승인 흐름 | delegate_task + 문서 상태 | 채팅으로 사람에게 제시 → 사람 승인 |
| 커뮤니케이션 | 구조화(intent 필수, 1라운드 규칙) | 구조화 + 캐주얼 대화 |

### team-of-one 변형 비교

| 관점 | Secretary | COO |
|------|-----------|-----|
| 주된 업무 | 정보 트리아지·대행 전송·문서 작성 | 위임 판단·부문 감시·경영 보고 |
| 대외 | 외부 채널(Gmail, Chatwork 등) | 원칙 없음(비서 경유) |
| 대내 | 정보 분배(라우팅) | 지휘 명령(위임·감사) |
| machine | 문서 작성·PDF화 | 조직 분석·KPI 집계·통계 집약 |
| 판단 성격 | 트리아지(분류) | 경영 판단(위임 vs 직접 대응 vs 에스컬레이션) |

### 설계 시 유의점

- **`call_human`이 주요 수단**: 사람에 대한 보고·확인 요청은 `call_human` 사용
- **캐주얼 커뮤니케이션**: 사무 처리뿐 아니라 사람과의 일상 대화도 책무에 포함
- **비서 고유**: 전송 전 승인(외부 채널 전송은 사람 승인 필요), 정보 트리아지(외부 수신 메시지 분류·분배)
- **COO 고유**: 라우팅 규칙(건너뛰기 지시 금지), 스팬 오브 컨트롤 관리, 탑레벨 동료 협력 패턴(재무·법무 합의)
