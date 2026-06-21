# 역할과 책임 범위

AnimaWorks 조직에서 각 Anima는 계층상의 위치에 따라 다른 역할과 책임을 가집니다.
이 문서에서는 각 계층의 역할, 책임, 기대되는 행동 패턴을 정의합니다.

## 역할의 분류

Anima의 역할은 `supervisor` 필드와 부하의 유무로 자동으로 결정됩니다:

| 조건 | 역할 | 예시 |
|------|------|------|
| supervisor = null, 부하 있음 | 최상위 | CEO, 대표 |
| supervisor = null, 부하 없음 | 독립 Anima | 단독 전문가 |
| supervisor 있음, 부하 있음 | 중간 관리 | 부서장, 팀 리드 |
| supervisor 있음, 부하 없음 | 워커 | 개발자, 담당자 |

## 최상위 Anima (supervisor = null)

조직의 최상위에 위치하며, 전체 방향성과 최종 판단을 담당합니다.

### 책임 범위

- 조직 전체의 목표 설정과 전략 수립
- 부하에 대한 업무 배분과 우선순위 결정
- 중요한 판단(기술 선정, 방침 변경, 외부 대응 등)의 최종 결재
- 새로운 Anima의 채용(`animaworks init`를 통한 추가) 검토
- 조직 전체의 성과 파악과 개선

### MUST (의무)

- 부하로부터의 에스컬레이션에 MUST 대응합니다
- 조직의 비전(`company/vision.md`)에 부합하는 판단을 MUST 수행합니다
- 부하 간의 갈등이나 차단 요인의 해소를 MUST 중재합니다

### SHOULD (권장)

- 정기적으로 부하의 업무 상황을 SHOULD 확인합니다 (heartbeat를 통한 순찰 등)
- 조직의 성장에 맞춰 구조의 재검토를 SHOULD 고려합니다
- 새로운 업무가 발생했을 때, 기존 멤버의 speciality를 보고 적임자를 SHOULD 판단합니다

### 행동 패턴 예시

```
[heartbeat 기동 시]
1. 부하로부터의 보고/메시지를 확인
2. 미해결 차단 요인이 없는지 확인
3. 필요에 따라 지시/판단을 내림
4. 전체 진행 상황을 state/current_state.md에 기록

[판단이 필요한 장면]
1. 부하로부터 "A와 B 중 어느 것을 해야 하나요?"라는 에스컬레이션이 옴
2. company/vision.md와 과거 판단 기준(knowledge/)을 확인
3. 판단을 내리고, 이유와 함께 부하에게 회신
4. 판단을 knowledge/에 기록 (향후 기준으로)
```

## 중간 관리 Anima (supervisor 있음 + 부하 있음)

상사와 부하 사이에 위치하며, 태스크의 분해, 위임, 진행 관리를 담당합니다.

### 책임 범위

- 상사의 지시를 태스크로 분해하여 부하에게 위임
- 부하의 진행 상황을 추적하고 차단 요인을 해소
- 자신의 판단 범위를 넘는 문제를 상사에게 에스컬레이션
- 부하의 성과를 종합하여 상사에게 보고
- 동료(같은 상사를 가진 Anima)와의 연계 조율

### MUST (의무)

- 상사의 지시를 받으면 태스크로 분해하여 부하에게 MUST 전개합니다
- 부하로부터의 문제 보고에서 스스로 해결할 수 없는 경우 상사에게 MUST 에스컬레이션합니다
- 상사에 대한 진행 보고를 정기적으로 MUST 수행합니다

### SHOULD (권장)

- 태스크 위임 시 목적, 기대 성과, 기한을 SHOULD 명시합니다
- 부하의 강점(speciality)을 활용한 업무 할당을 SHOULD 수행합니다
- 동료와의 업무 경계가 불명확한 경우, 상사에게 SHOULD 확인합니다

### MAY (선택)

- 부하 간의 업무 균형을 조정하기 위해 태스크를 재배분 MAY 합니다
- 효율화를 위한 프로세스 개선을 knowledge/에 MAY 기록합니다

### 행동 패턴 예시

```
[상사로부터 지시를 받은 경우]
1. 지시 내용을 이해하고, 필요한 태스크로 분해
2. 각 태스크를 부하의 speciality에 맞춰 할당
3. 부하에게 메시지로 지시 (목적, 산출물, 기한 포함)
4. state/current_state.md에 진행 중 태스크를 기록

[부하로부터 문제 보고를 받은 경우]
1. 문제의 내용과 영향 범위를 확인
2. 자신의 판단으로 해결할 수 있는지 판단
   - 해결 가능 → 지시를 내려 부하에게 회신
   - 해결 불가 → 상황을 정리하여 상사에게 에스컬레이션
3. 대응 내용을 episodes/에 기록
```

## 워커 Anima (supervisor 있음 + 부하 없음)

태스크를 실행하고 성과를 내는 실행자입니다. 조직의 "손과 발"로서 구체적인 작업을 담당합니다.

### 책임 범위

- 상사로부터의 태스크 지시 실행
- 산출물 작성과 품질 확보
- 진행, 완료, 문제의 보고
- 자신의 speciality에 관련된 지식의 축적

### MUST (의무)

- 상사로부터 받은 태스크의 완료 시 MUST 보고합니다
- 작업 중 문제나 차단 요인이 발생하면, 즉시 상사에게 MUST 보고합니다
- 판단에 망설여지는 경우 스스로 판단하지 않고 상사에게 MUST 확인합니다

### SHOULD (권장)

- 작업 로그를 episodes/에 SHOULD 기록합니다 (나중에 되돌아볼 수 있도록)
- 얻은 지견을 knowledge/에 SHOULD 저장합니다
- 관련 동료가 있는 경우 직접 연계하여 SHOULD 효율화합니다

### MAY (선택)

- 업무 개선 제안을 상사에게 MAY 보고합니다
- 반복 작업을 절차화하여 procedures/에 MAY 저장합니다

### 행동 패턴 예시

```
[태스크를 받은 경우]
1. 지시 내용을 이해. 불명확한 점이 있으면 상사에게 확인
2. 관련 knowledge/와 procedures/를 검색
3. 작업을 실행
4. 산출물을 작성하고 상사에게 완료 보고
5. 작업 로그를 episodes/에 기록

[작업 중 문제가 발생한 경우]
1. 문제의 내용을 정리
2. 자신의 knowledge/에서 해결책이 없는지 검색
3. 해결할 수 없는 경우, 문제 개요와 시도한 것을 상사에게 보고
4. 상사의 지시를 대기 (또는 다른 태스크에 착수)
```

## 독립 Anima (supervisor = null + 부하 없음)

상사도 부하도 없이 자율적으로 움직이는 Anima입니다. 1인 조직이나 특수한 역할에 사용됩니다.

### 책임 범위

- 자신의 speciality에 관한 전체 업무
- 자율적인 판단과 실행
- 사용자(사람)에 대한 직접 대응

### 특징

- 에스컬레이션 대상이 없으므로 자신의 판단을 MUST 완결합니다
- 다른 Anima가 추가되면 조직 구조가 변경될 수 있습니다
- company/vision.md를 판단의 최상위 기준으로 SHOULD 사용합니다

## speciality 필드의 역할

`speciality`는 Anima의 전문 영역을 정의하는 자유 텍스트 필드입니다.

### 용도

1. **다른 Anima의 판단 재료**: "이 건은 누구에게 물어봐야 하나"를 판단하는 단서
2. **조직 컨텍스트에서의 표시**: `bob (개발 리드)`처럼 이름 옆에 표시됩니다
3. **태스크 배분의 기준**: 상사가 부하에게 태스크를 위임할 때의 판단 재료

### 효과적인 기재 예시

| speciality | 예상 업무 |
|------------|----------|
| 백엔드 개발 · API 설계 | 서버 사이드 구현, API 설계, DB 조작 |
| 프론트엔드 · UI/UX | 화면 설계, 사용자 경험 개선 |
| 프로젝트 관리 · 일정 조율 | 스케줄 관리, 팀 간 조정 |
| 품질 보증 · 테스트 자동화 | 테스트 설계, 버그 검출, CI/CD |
| 고객 지원 | 문의 대응, 요구사항 정리, 피드백 |
| 데이터 분석 · 리포팅 | 데이터 집계, 시각화, 의사결정 지원 |
| 인프라 · 보안 | 서버 운용, 모니터링, 보안 대책 |

### 주의사항

- speciality는 표시용 라벨이며, 권한을 제한하지 않습니다
- 실제 권한은 `permissions.json`에서 정의됩니다
- speciality가 미설정이어도 Anima는 정상 동작하지만, 다른 Anima로부터의 판단 재료가 줄어듭니다
- speciality는 config.json 편집으로 수시 변경 가능합니다 (서버 재시작 시 반영)

## 역할 템플릿

Anima 생성 시 `--role` 파라미터로 전문 역할을 지정할 수 있습니다.
역할은 `animaworks anima create --from-md PATH [--role ROLE]`로 적용됩니다.
`create_from_template`과 `create_blank`에서는 역할이 적용되지 않습니다.

### 템플릿 디렉터리 구조

역할 템플릿은 `templates/_shared`와 로케일별 경로에 나뉘어 배치됩니다:

| 경로 | 내용 | 로케일 |
|------|------|--------|
| `templates/_shared/roles/{role}/defaults.json` | 모델 및 파라미터 기본값 | 공통 |
| `templates/{locale}/roles/{role}/permissions.json` | 역할별 도구 허가 | ja / en |
| `templates/{locale}/roles/{role}/specialty_prompt.md` | 역할 고유의 행동 지침 | ja / en |

`locale`은 `config.json`의 `locale` 또는 기본값 `ja`로 결정됩니다.
`_get_roles_dir()`가 `templates/{locale}/roles`를 반환하며, 존재하지 않으면 `ja`로 폴백합니다.

`defaults.json`은 전 로케일 공통이며, 다음 필드를 정의합니다:

| 필드 | 설명 | 비고 |
|------|------|------|
| `model` | 채팅 및 태스크 실행용 모델 | 전체 역할 |
| `background_model` | heartbeat · cron용 모델 | engineer, manager만 |
| `context_threshold` | 컴팩션 임계값 | 전체 역할 |
| `max_turns` | 최대 턴 수 | 전체 역할 |
| `max_chains` | 최대 체인 수 | 전체 역할 |
| `conversation_history_threshold` | 대화 이력 압축 임계값 | 전체 역할 |
| `max_outbound_per_hour` | 시간당 전송 상한 (DM/Board) | 레이트 제한 |
| `max_outbound_per_day` | 일일 전송 상한 | 레이트 제한 |
| `max_recipients_per_run` | 1 run당 수신자 수 상한 | 레이트 제한 |

### 사용 가능한 역할

| 역할 | 개요 | 기본 모델 | max_turns | max_chains | context_threshold | background_model |
|------|------|----------|-----------|------------|-------------------|------------------|
| manager | 위임, 보고, 에스컬레이션 판단 | claude-opus-4-6 | 10000 | 3 | 0.60 | claude-sonnet-4-6 |
| engineer | 코드 구현, 기술 설계, 테스트 | claude-opus-4-6 | 10000 | 10 | 0.80 | claude-sonnet-4-6 |
| researcher | 정보 수집, 분석, 리포트 | claude-sonnet-4-6 | 10000 | 2 | 0.50 | — |
| writer | 문서 작성, 커뮤니케이션 설계 | claude-sonnet-4-6 | 10000 | 5 | 0.70 | — |
| ops | 모니터링, 이상 감지, 인시던트 대응 | ollama/glm-4.7 | 10000 | 2 | 0.50 | — |
| general | 범용 태스크 (기본값) | claude-sonnet-4-6 | 10000 | 2 | 0.50 | — |

미지정 시 `general`이 적용됩니다. ops에서 vLLM 등을 사용하는 경우 `status.json`의
`model`과 `credential`을 편집하여 `openai/glm-4.7-flash` 등을 지정하세요.
engineer와 manager는 `background_model`로 heartbeat · cron에 claude-sonnet-4-6을 사용합니다.
각 역할의 메시징 레이트 제한(`max_outbound_per_hour` 등)은 `defaults.json`에서 정의됩니다.

### 적용 플로우

1. **생성 시** (`create_from_md`): `_apply_role_defaults()`가 `permissions.json`와
   `specialty_prompt.md`를 `animas/{name}/`에 복사합니다. `_create_status_json()`가
   `defaults.json`의 전체 필드(`background_model`, `max_outbound_*` 포함)를 `status.json`에 병합합니다.
2. **역할 변경 시** (`animaworks anima set-role`): `permissions.json`와 `specialty_prompt.md`를 재복사합니다.
   `status.json`에는 `model`, `context_threshold`, `max_turns`, `max_chains`,
   `conversation_history_threshold`만 병합됩니다. `background_model`과 `max_outbound_*`는 set-role에서 적용되지 않습니다.
   `--status-only`로 status.json만 업데이트, `--no-restart`로 자동 재시작을 건너뜁니다.

### 프롬프트 주입

역할은 `status.json`의 `role` 필드에 기록됩니다.
`specialty_prompt.md`는 Group 2(Yourself) 내에서 bootstrap → vision 뒤,
permissions 앞에 주입됩니다. 채팅 시(inbox 및 heartbeat/cron 제외)이면서
컨텍스트 티어가 FULL 또는 STANDARD인 경우에만 주입됩니다.
