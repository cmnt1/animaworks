# Cron: {name}

<!--
=== Cron 형식 사양 ===

■ 기본 구조
  ## 작업 이름
  schedule: <5필드 cron식>
  type: llm | command
  (본문 또는 command/tool 정의)

■ schedule: 은 필수
  각 작업(## 제목) 바로 뒤에 `schedule:` 줄을 작성할 것.
  생략하면 작업이 실행되지 않는다.

■ 5필드 cron식
  schedule: 분 시 일 월 요일
  ┌───── 분 (0-59)
  │ ┌───── 시 (0-23)
  │ │ ┌───── 일 (1-31)
  │ │ │ ┌───── 월 (1-12)
  │ │ │ │ ┌───── 요일 (0=월 ~ 6=일)
  │ │ │ │ │
  * * * * *

■ 자주 쓰는 스케줄 예시
  schedule: 0 9 * * *       # 매일 아침 9:00
  schedule: */5 * * * *     # 5분마다
  schedule: 0 9 * * 0-4     # 평일 9:00 (월~금)
  schedule: 0 17 * * 4      # 매주 금요일 17:00
  schedule: 0 2 * * *       # 매일 2:00
  schedule: 30 12 1 * *     # 매월 1일 12:30

■ 하면 안 되는 작성법
  ✗ ### cron식          ← 제목 레벨은 ##만 사용
  ✗ schedule: 매일 아침 9시   ← 자연어 금지, 5필드 cron식으로 작성
  ✗ (schedule: 줄 없음) ← 반드시 작성할 것

■ type의 종류
  1. LLM형 (type: llm) - 판단·사고가 필요한 작업
  2. Command형 (type: command) - 결정적인 bash/tool 실행

■ 옵션 (command형만)
  skip_pattern: <정규식>       — stdout이 매치되면 LLM 분석 스킵
  trigger_heartbeat: false     — 출력이 있어도 LLM 분석을 트리거하지 않음

■ 상세 참조
  → common_skills/cron-management.md 참조
-->

## 매일 아침 업무 계획
schedule: 0 9 * * *
type: llm
장기 기억에서 어제의 진행 상황을 확인하고 오늘의 작업을 계획한다.
이념과 목표에 비추어 우선순위를 판단한다.
결과는 state/current_state.md에 기록한다.

## 주간 회고
schedule: 0 17 * * 4
type: llm
이번 주의 episodes/를 다시 읽고 패턴을 추출하여 knowledge/에 통합한다.
(기억의 통합 = 뇌과학에서 말하는 수면 중 기억 고정화)

<!--
## 백업 실행
schedule: 0 2 * * *
type: command
command: /usr/local/bin/backup.sh

## Slack 알림
schedule: 0 9 * * 0-4
type: command
tool: slack_send
args:
  channel: "#general"
  message: "좋은 아침입니다!"
-->
