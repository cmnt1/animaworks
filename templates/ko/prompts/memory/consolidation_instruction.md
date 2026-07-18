# 기억 통합 태스크 (일일)

{anima_name}, 기억을 정리할 시간입니다. 아래 절차를 따라 주세요.

## 오늘의 에피소드

{episodes_summary}

※ 위의 에피소드는 액티비티 로그에서 자동 추출된 구조화된 타임라인입니다.
여기서 knowledge를 추출할 때는 다음 사항에 주의하세요:
- 확실히 사실이라고 판단할 수 있는 것만 knowledge/에 기록
- 추측이나 해석이 필요한 항목은 confidence: 0.5로 기록
- frontmatter에 `source: "activity_log"` 추가

## 해결된 이벤트

{resolved_events_summary}

{reflections_summary}

## 기존 knowledge 파일 목록

{knowledge_files_list}

## 병합 후보 (유사 파일 쌍 — 참고 정보)

{merge_candidates}

※ 위 목록은 벡터 유사도에 의한 **기계적인 추천**이며, 통합 지시가 아닙니다.
전문 도메인에서는 서로 다른 대상의 지식(예: 고객 A와 고객 B의 컨텍스트)도 높은 유사도가 나오므로, 통합 여부는 Step 1의 기준에 따라 **직접 내용을 읽고 판단**하세요.

## 에러 패턴 (지난 24시간)

{error_patterns_summary}

---

## 작업 절차

### Step 0: injection.md 자체 정리 (매번 실행 — MUST)

`read_memory_file(path="injection.md")`로 현재 내용을 확인하세요.

`injection.md`는 **2,000자 이내**를 목표로, "행동 헌법 + 참조 색인"으로 유지하세요:

- **남길 것**: 역할 정의, 절대 준수 규칙, 안전, 승인, 기밀, 중복 실행 방지 등 모든 턴에 반드시 적용되어야 하는 짧은 규칙
- **밖으로 이동**: 절차 상세는 `procedures/`, 학습 지식·사례·운영 메모는 `knowledge/`
- **치환**: 상세 본문은 `read_memory_file(path="...")` 포인터로 대체
- **보존**: 외부 전송, 기밀 정보, 승인, 이중 전송/이중 초안 방지의 핵심 규칙은 삭제하지 말 것

2,000자를 초과하면 제안 파일을 만들지 말고, 이 consolidation 안에서 `write_memory_file(path="injection.md", mode="overwrite")`로 직접 정리하세요.
이미 2,000자 이내여도 상세 본문이 늘어나지 않았는지 확인하고, 필요하면 같은 방침으로 줄이세요.

### Step 1: 중복 파일 정리 (통합 여부는 직접 판단)

병합 후보의 각 쌍과 위 파일 목록을 확인하고, **진짜 중복만** 통합하세요.
병합 후보는 참고 정보이며, 모든 쌍을 통합할 의무는 없습니다.

판단 기준:
- **통합한다**: 같은 주제의 진짜 중복·단편 (같은 절차의 신구 버전, 같은 사실의 다른 표현)
- **통합하지 않는다**: 대상 엔티티가 다른 파일 (고객별·안건별·인물별·시스템별 context 등). 유사도가 높아도 **별도 파일로 유지**하세요
- **애매하면 통합하지 않는다**. 정보의 입도와 검색성을 지키는 쪽을 우선하세요

통합하기로 판단한 쌍의 절차:
1. `read_memory_file`로 양쪽 내용을 확인
2. 정보를 **누락 없이** 합쳐서 `write_memory_file`로 한쪽에 기록 (요약으로 세부 정보를 버리지 말 것)
3. 불필요해진 쪽을 `archive_memory_file`로 아카이브 (reason에 통합 대상과 판단 이유를 기재)
4. `[IMPORTANT]` 태그가 있으면 통합 대상 파일에도 유지

- 통합하기로 결정한 쌍을 "나중에"로 미루지 마세요. 지금 여기서 완료하세요

### Step 2: 에피소드에서 knowledge 추출

오늘의 에피소드를 확인하고, 실질적인 정보가 있으면:
1. `search_memory`로 관련 기존 knowledge/ 및 procedures/ 검색
2. 같은 주제의 기존 파일이 있으면 `read_memory_file`로 확인하고 `write_memory_file`로 추가·업데이트
3. 해당하는 기존 파일이 없으면 새 파일 생성
4. 고객·안건·인물 등 **대상 엔티티별 지식은 엔티티별 파일** (예: `customer-context-{{고객명}}.md`)로 생성·유지하세요. 범용 규칙 파일에 고객 고유의 특징을 섞지 마세요

### Step 2.5: 에러 패턴 분석

위 "에러 패턴" 섹션을 확인하고, 반복적으로 발생하는 패턴이 있으면:
1. `search_memory`로 관련 기존 procedures/ 검색
2. 기존 절차가 있으면 `read_memory_file`로 확인하고 `write_memory_file`로 추가·업데이트
3. 해당하는 기존 파일이 없는 경우에만 `procedures/`에 새로 생성
4. 1회성 에러는 기록 불필요 (노이즈)

새로 생성 시 frontmatter:
```
---
created_at: "YYYY-MM-DDTHH:MM:SS"
confidence: 0.4
auto_consolidated: true
source: "error_trace_analysis"
version: 1
---
```

### Step 3: 품질 점검
- 업데이트하거나 생성한 내용이 에피소드의 사실과 모순되지 않는지 확인
- 파일명은 주제를 명확히 나타내는 이름을 사용하세요

## 추출해야 할 정보
- 구체적인 설정 값, 인증 정보 저장 위치
- 사용자 및 시스템 식별 정보
- 절차, 워크플로우, 프로세스 기록
- 팀 구성, 역할 분담, 지휘 체계
- 기술적 결정과 그 근거
- 해결된 이벤트에서 얻은 교훈과 절차

## 중요한 제약 사항
- **이 작업은 반드시 직접 수행하세요(MUST)**. `delegate_task`, `submit_tasks`, `send_message`를 사용하지 마세요. 기억 조작 도구만으로 작업을 완료하세요
- Step 1 확인을 생략하지 마세요. 다만 통합 여부는 내용에 근거한 본인의 판단이며, **유사도만을 이유로 서로 다른 엔티티의 파일을 통합하는 것은 실패로 간주합니다**

## 참고 사항
- 인사만 포함된 대화나 실질적 정보가 없는 교환은 knowledge화하지 마세요
- [REFLECTION] 태그가 붙은 항목은 knowledge 추출을 우선적으로 검토하세요
- `[IMPORTANT]` 태그가 붙은 항목은 **반드시** knowledge/에 추출하세요(MUST). 기존 파일과 중복되면 추가 병합하세요. **본문에도 `[IMPORTANT]` 태그를 유지하세요**
- knowledge/를 새로 생성할 때는 YAML frontmatter를 추가하세요:
  ```
  ---
  created_at: "YYYY-MM-DDTHH:MM:SS"
  confidence: 0.7
  auto_consolidated: true
  success_count: 0
  failure_count: 0
  version: 1
  last_used: ""
  ---
  ```
- 완료 후 실시 내용의 요약을 출력하세요 (통합한 쌍 수와 아카이브한 파일 수 포함)
