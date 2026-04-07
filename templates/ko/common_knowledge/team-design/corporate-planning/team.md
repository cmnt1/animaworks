# 경영기획 풀 팀 — 팀 개요

## 3개 역할 구성

| 역할 | 책임 | 권장 `--role` | `speciality` 예 | 상세 |
|--------|------|--------------|-----------------|------|
| **Corporate Strategist** | 전략 판단·사업 환경 분석(machine)·OKR 관리·최종 승인 | `manager` | `corporate-strategist` | `corporate-planning/strategist/` |
| **Business Analyst** | 시장/경쟁 데이터 수집·구조화 분석(machine) | `researcher` | `business-analyst` | `corporate-planning/analyst/` |
| **Strategy Coordinator** | 독립 검증(machine)·부서 간 조정·KPI 추적 | `administration` | `strategy-coordinator` | `corporate-planning/coordinator/` |

한 Anima에 전 과정을 몰아넣으면 전략 판단의 편향(낙관 편향)·조치의 소실(silent drop)·컨텍스트 비대화가 발생한다.

각 역할 디렉터리에는 `injection.template.md`(injection.md 초안), `machine.md`(machine 활용 패턴), `checklist.md`(품질 체크리스트)가 있다.

> 기본 원칙 상세: `team-design/guide.md`

## 핸드오프 체인

```
Analyst (트렌드·경쟁·시장 데이터 수집 → machine으로 구조화)
  → market-analysis.md → Strategist
    → Strategist → strategic-plan.md (approved)
      → machine으로 사업 분석(이길 수 있는 영역 추출)
        → strategy-report.md (reviewed)
          → Coordinator (독립 검증[machine]: KPI 실태와의 정합 + 실행 가능성)
            └─ 지적 있음 → Strategist에게 반려
            └─ APPROVE → Strategist → Tracker 갱신 → call_human → 사람이 최종 확인
```

### 인수인계 문서

| 송신 → 수신 | 문서 | 조건 | 통신 수단 |
|----------------|------------|------|---------|
| Strategist → Analyst | 조사 의뢰 | | `delegate_task` |
| Analyst → Strategist | `market-analysis.md` | `status: approved` | `send_message (intent: report)` |
| Strategist → Coordinator | `strategy-report.md` | `status: reviewed` | `send_message (intent: report)` |
| Coordinator → Strategist | `verification-report.md` | `status: approved` | `send_message (intent: report)` |
| Coordinator → 각 부서 | 조치 전달 | Strategist 승인 후 | `send_message` |
| Strategist → COO / 상위 | 최종 보고 | 전 승인 후 | `send_message (intent: report)` |

### 운영 규칙

- **수정 사이클**: Critical → 전면 재분석(Analyst에 재조사 + Coordinator에 재검증) / Warning → 차분 확인만 / 3왕복으로 해소되지 않음 → 사람에게 에스컬레이션
- **Tracker 규칙**: Strategic Initiative Tracker의 전 항목을 다음 리뷰 시 갱신한다. silent drop(언급 없이 소멸)은 금지
- **machine 실패 시**: `current_state.md`에 기록 → 다음 heartbeat에서 재평가

## 스케일링

| 규모 | 구성 | 비고 |
|------|------|------|
| 솔로 | Strategist가 전 역할 겸임(checklist로 품질 보증) | 단일 프로젝트 전략 리뷰 |
| 페어 | Strategist + Coordinator | 검증의 독립성을 확보하고 싶을 때 |
| 풀 팀 | 본 템플릿대로 3명 | 풀 전략 사이클(조사→분석→검증→실행 추적) |
| 스케일드 | Strategist + 복수 Analyst(영역별) + Coordinator | 복수 사업 영역의 동시 분석 |

## 타 팀과의 대응 관계

| 개발 팀 역할 | 법무 팀 역할 | 경영기획 팀 역할 | 대응하는 이유 |
|----------------|----------------|---------------------|-------------|
| PdM(조사·계획·판단) | Director(분석 계획·판단) | Strategist(전략 판단) | 「무엇을 할지」를 결정하는 사령탑 |
| Engineer(구현) | Director + machine(계약서 스캔) | Strategist + machine(사업 분석) | machine으로 분석을 실행 |
| Reviewer(정적 검증) | Verifier(독립 검증) | Coordinator(독립 검증) | 「실행과 검증의 분리」의 핵. machine으로 편향 없는 검증 |
| Tester(동적 검증) | Researcher(근거 검증) | Analyst(데이터 수집·분석) | 외부 데이터로 뒷받침을 취한다 |

## Strategic Initiative Tracker — 이니셔티브 추적표

이니셔티브 진행을 추적하고 silent drop을 구조적으로 방지한다.

### 추적 규칙

- 새 이니셔티브가 발생하면 이 표에 등록한다
- 다음 리뷰 시 전 항목의 status를 갱신한다
- 정체(1개월 이상 스테이지 변화 없음)는 Strategist에 보고한다
- silent drop(언급 없이 소멸)은 금지

### 템플릿

```markdown
# 이니셔티브 추적표: {팀명}

| # | 이니셔티브 | 오너 | 스테이지 | 시작일 | 기한 | 비고 |
|---|------------|---------|---------|--------|------|------|
| SI-1 | {명칭} | {부서/이름} | {스테이지} | {날짜} | {날짜} | {특기} |

스테이지 범례:
- 기획 중: 전략 검토 중
- 승인됨: 실행 시작 대기
- 실행 중: 조치 진행 중
- 리뷰: 효과 측정 중
- 완료: 목표 달성
- 중단: 사유를 비고에 기록
```

## cron 설정 예

| 태스크 | schedule 예 | type | 개요 |
|--------|------------|------|------|
| 월간 리뷰 | `0 10 1 * *` | llm | Tracker 전건 리뷰 + 진행 분석 |
