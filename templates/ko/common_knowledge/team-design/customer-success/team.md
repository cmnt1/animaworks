# CS(고객 성공) 풀 팀 — 팀 개요

## 2개 역할 구성

| 역할 | 책임 | 권장 `--role` | `speciality` 예 | 상세 |
|------|------|--------------|-----------------|------|
| **CS Lead** | 고객 전략·온보딩 계획[machine]·헬스 분석[machine]·리텐션 시책[machine]·VoC 집약[machine]·에스컬레이션 | `manager` | `cs-lead` | `customer-success/cs-lead/` |
| **Support** | 티켓 대응·FAQ 관리·온보딩 실행·1차 대응·VoC 소재 수집 | `administration` | `cs-support` | `customer-success/support/` |

한 Anima에 전 과정을 몰아넣으면 고객 분석과 1차 대응의 컨텍스트 경쟁·헬스 판정의 자기 검증 사각·VoC 집약과 티켓 대응의 우선순위 충돌이 발생합니다.

각 역할 디렉터리에 `injection.template.md`(injection.md 초안), `machine.md`(machine 활용 패턴, CS Lead만), `checklist.md`(품질 체크리스트)가 있습니다.

> 기본 원칙 상세: `team-design/guide.md`

## 2가지 실행 모드

### Onboarding mode(계획 기반)

```
영업 Director → cs-handoff.md (draft)
  → CS Lead → Phase A: machine으로 온보딩 계획 → CS Lead가 검증
    → onboarding-plan.md (approved) → delegate_task → Support
      → Support: 온보딩 실행 → CS Lead에 완료 보고
```

영업 팀에서 계약 성립 시 `cs-handoff.md`를 받아, CS Lead가 machine으로 고객 분석·온보딩 계획을 작성한 후 Support에 실행을 위임합니다.

### Maintenance mode(정기 순회 기반)

```
CS Lead → Phase B: Health Tracker 정기 분석 (heartbeat/cron)
  → Yellow/Red 검출 → Phase C: machine으로 리텐션 시책 드래프트 → CS Lead가 검증 → 고객 대응
  → Critical → 상위에 에스컬레이션
  → 전부 Green → 경과 관찰

CS Lead → Phase D: VoC 집약 (cron: 정기)
  → voc-report.md → COO 경유로 개발 팀에 피드백

Support → 티켓 대응 + FAQ 관리 (cron: 일상)
  → 문제 발생 → CS Lead에 보고
  → CS 문의 외(영업 등) → 해당 팀에 에스컬레이션
```

## 핸드오프 체인

```
영업 Director → cs-handoff.md (draft)
  → CS Lead → Phase A: machine 분석·계획 → CS Lead가 검증
    → onboarding-plan.md (approved) → delegate_task → Support
      → Support: 온보딩 실행 → CS Lead에 완료 보고
        → CS Lead: Health Tracker에 신규 등록 → Maintenance mode로

CS Lead → Phase B: Health Tracker 분석 (heartbeat/cron)
  → Yellow/Red → Phase C: machine 리텐션 시책 → CS Lead가 검증 → 실행
  → Phase D: VoC 집약 → voc-report.md → COO

Support → 자율 순회 (cron)
  → 티켓 대응 → CS Lead에 보고
```

### 인수인계 문서

| 송신 → 수신 | 문서 | 조건 | 통신 수단 |
|-------------|------|------|----------|
| 영업 Director → CS Lead | `cs-handoff.md` | 계약 성립 시 | `send_message (intent: report)` |
| CS Lead → Support | `onboarding-plan.md` | `status: approved` | `delegate_task` |
| Support → CS Lead | 티켓 보고 | 문제 발생 시 | `send_message (intent: report)` |
| CS Lead → COO | `voc-report.md` | 정기(cron) | `send_message (intent: report)` |
| CS Lead → 상위 | 에스컬레이션 | Critical 헬스 스코어 | `send_message (intent: report)` |

### 운영 규칙

- **수정 사이클**: Critical → 즉시 개입 + 상위 에스컬레이션 / Warning → 리텐션 시책 수립 / 3왕복으로 해소 안 됨 → 사람에게 에스컬레이션
- **Customer Health Score Tracker**: 고객 헬스 스코어를 추적. silent drop 금지
- **에스컬레이션 3계층**: Support → CS Lead → 상위(COO 등)
- **machine 실패 시**: `current_state.md`에 기록 → 다음 heartbeat에서 재평가

## 스케일링

| 규모 | 구성 | 비고 |
|------|------|------|
| 솔로 | CS Lead가 전 역할 겸임(checklist로 품질 보증) | 소수 고객, 정형 대응 |
| 페어 | 본 템플릿대로 2명 | 표준 운영 |
| 스케일 | CS Lead + 복수 Support(세그먼트별 등) | 대규모 고객 기반 |

## 다른 팀과의 대응 관계

| 개발 팀 역할 | 법무 팀 역할 | 영업·MKT 역할 | CS 역할 | 대응 이유 |
|-------------|-------------|-------------|---------|----------|
| PdM(계획·판단) | Director(분석 계획·판단) | Director(전략·영업 실행) | CS Lead(고객 전략·분석) | 「무엇을 할지」 결정하는 사령탑 |
| Engineer(구현) | Director + machine | Director + machine | CS Lead + machine | machine으로 분석·제작을 실행 |
| Reviewer(정적 검증) | Verifier(독립 검증) | {컴플라이언스 리뷰어명}(컴플라이언스) | — | CS에서는 독립 검증 역할 불요(대응 품질은 KPI로 보장) |
| Tester(동적 검증) | Researcher(근거 검증) | Researcher(시장 조사) | Support(1차 대응·정보 수집) | 고객 접점에서 정보를 수집 |

## KPI 체계(4지표)

| 지표 | 개요 | AI CS에서의 위치 |
|------|------|-----------------|
| **CSAT** | 고객 만족도 점수 | 서베이 기반. 대응 품질의 직접 지표 |
| **NPS** | 넷 프로모터 스코어 | 추천 의향. 장기 고객 관계 지표 |
| **이탈률** | 해지율 | Health Tracker의 Yellow/Red로 징후 검출 |
| **온보딩 완료율** | 신규 고객 초기 설정 완료율 | cs-handoff.md 수령 → 온보딩 완료까지 추적 |

시간 기반 KPI(초기 응답 시간, 해결 시간 등)는 AI 에이전트 CS에서 즉시 응답(≈ 0)이므로 제외합니다.

## Customer Health Score Tracker — 고객 헬스 스코어 추적표

고객의 헬스 스코어를 추적합니다. Yellow/Red 검출 시 Phase C에서 리텐션 시책을 수립합니다.

### 추적 규칙

- 신규 고객은 온보딩 완료 후 이 표에 등록합니다
- 다음 Heartbeat / 리뷰 시 전 항목의 상태를 갱신합니다
- Yellow/Red 고객은 Phase C에서 리텐션 시책을 수립합니다
- silent drop(언급 없이 소멸)은 금지입니다

### 템플릿

```markdown
# 고객 헬스 스코어 추적표: {팀명}

| # | 기업명 | 헬스 스코어 | 최종 대응일 | 다음 액션 | 비고 |
|---|--------|-----------|----------|----------|------|
| CS-1 | {명칭} | {Green/Yellow/Red} | {날짜} | {액션} | {특기} |

헬스 스코어 범례:
- Green: 정상(활발한 이용, CSAT 양호, 문의 적음)
- Yellow: 주의(이용 감소 추세, 미응답 서베이, 문의 증가)
- Red: 위험(이용 중단, CSAT 저하, 이탈 징후)
```
