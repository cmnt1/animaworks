# common_knowledge 참조 경로

Anima가 common_knowledge에 접근하는 5가지 경로와 백그라운드의 RAG 인덱스 구축 메커니즘.

---

## 참조 경로의 전체 구조

| # | 경로 | 유형 | Anima의 인식 |
|---|------|--------|------------|
| 1 | 시스템 프롬프트 힌트 | 자동 | 힌트를 보고 능동적으로 접근 |
| 2 | Priming Channel C | 자동 | 관련 지식으로 자동 표시 |
| 3 | `search_memory` 도구 | 능동 | scope 지정으로 명시적 검색 |
| 4 | `read_memory_file` / `write_memory_file` | 능동 | 경로 지정으로 직접 접근 |
| 5 | Claude Code 직접 파일 I/O (Mode S) | 능동 | Read/Write 등으로 직접 접근 |

---

## 경로 1: 시스템 프롬프트에 힌트 주입

`builder.py`이 시스템 프롬프트 구축 시, `~/.animaworks/common_knowledge/`에 파일이 존재하는 경우 **힌트 텍스트**를 Group 4 (기억과 능력)에 주입한다.

- **주입 시점**: 프롬프트 구축 시 (자동)
- **내용**: common_knowledge의 존재와 사용법에 대한 힌트 (파일 내용은 포함하지 않음)
- **제외 조건**: `is_task=True` (TaskExec)의 경우 생략됨
- **Anima의 행동**: 힌트를 보고 `search_memory`이나 `read_memory_file`로 능동적으로 접근

## 경로 2: Priming Channel C / C0 — RAG 벡터 검색

`PrimingEngine`이 메시지의 키워드에서 자동으로 벡터 검색을 수행하고, 개인 knowledge와 공유 common_knowledge를 통합하여 시스템 프롬프트에 주입한다.

- **Channel C 예산**: 1200토큰
- **Channel C0 예산**: 300토큰 (`[IMPORTANT]` 태그가 붙은 청크의 개요 포인터 전용)
- **검색 대상**: `shared_common_knowledge` 컬렉션 (ChromaDB)
- **병합 방법**: 개인 knowledge의 검색 결과와 점수로 병합·정렬
- **신뢰도 분리**: Channel C의 결과는 trust 레벨로 분리됨 (medium / untrusted). 외부 플랫폼에서 유래한 청크는 untrusted로 처리됨
- **Anima의 행동**: 관련된 common_knowledge의 조각이 Priming 섹션에 자동 표시됨

### 주의점
- 1200토큰의 제약이 있으므로 전체 텍스트가 아닌 관련 조각만 표시됨
- common_knowledge의 문서 수가 늘어나면 개인 knowledge의 청크가 밀려날 위험이 있음
- `[IMPORTANT]` 청크는 Channel C0에서 항상 주입되므로 중요한 업무 규칙의 확실한 회상에 유효함

## 경로 3: `search_memory` 도구

Anima가 `search_memory(query="...", scope="common_knowledge")`을 호출하면 키워드 검색과 벡터 검색의 하이브리드로 common_knowledge를 검색한다.

- **키워드 검색**: `~/.animaworks/common_knowledge/` 내의 .md 파일을 텍스트 스캔
- **벡터 검색**: `shared_common_knowledge` 컬렉션을 검색
- **scope 지정**: `knowledge` / `episodes` / `procedures` / `common_knowledge` / `skills` / `activity_log` / `all`. `"common_knowledge"`로 한정 검색, `"all"` (기본값)에도 포함됨
- **`scope="all"`**: 벡터 검색의 각종 컬렉션에 더해 **activity_log의 BM25 결과를 RRF (Reciprocal Rank Fusion)로 통합**한다. 광범위 검색 시 최근 행동 로그도 후보에 포함됨

### 사용 예
```
search_memory(query="メッセージ 送信", scope="common_knowledge")
search_memory(query="レート制限", scope="all")
```

## 경로 4: `read_memory_file` / `write_memory_file`

Anima가 `read_memory_file(path="common_knowledge/...")`을 호출하면 경로 접두사를 감지하여 `~/.animaworks/common_knowledge/`으로 해석한다.

- **읽기**: 모든 Anima가 접근 가능
- **쓰기**: 모든 Anima가 접근 가능 (공유 지식 축적용)
- **경로 트래버설 방어**: `is_relative_to` 체크로 common_knowledge 외부로의 접근을 방지

### 사용 예
```
read_memory_file(path="common_knowledge/00_index.md")
write_memory_file(path="common_knowledge/operations/new-guide.md", content="...")
```

## 경로 5: Claude Code 직접 파일 I/O (Mode S만)

Mode S에서는 Claude Code의 내장 도구 (Read, Write, Grep, Glob 등)로 `~/.animaworks/common_knowledge/`에 직접 접근할 수 있다.

- **권한**: `handler_perms.py`에서 공유 읽기 전용 디렉터리로 허용
- **대상 모드**: Mode S (Agent SDK)만

---

## 백그라운드: RAG 인덱스 구축

common_knowledge가 벡터 검색 (경로 2·3)에서 발견되려면 ChromaDB에 인덱스되어 있어야 한다.

### 인덱스 시점

1. **Anima 시작 시**: `MemoryManager` 초기화 시 `_ensure_shared_knowledge_indexed()`이 호출되어 SHA-256 해시로 변경을 감지. 변경이 있으면 `shared_common_knowledge` 컬렉션에 재인덱스
2. **일일 04:00**: `_run_daily_indexing()`에서 모든 Anima의 벡터 DB를 증분 인덱스 업데이트. common_knowledge도 이 시점에 재인덱스됨

### 청킹 전략

`memory_type="common_knowledge"`의 경우 knowledge와 동일한 **Markdown 헤딩 구분**으로 청킹된다.

### 컬렉션 이름

`shared_common_knowledge` (모든 Anima 공유의 단일 컬렉션)

---

## reference/와의 차이

| 항목 | common_knowledge | reference |
|------|-----------------|-----------|
| RAG 인덱스 | 대상 (`shared_common_knowledge`) | **비대상** |
| `search_memory` | `knowledge` / `episodes` / `procedures` / `common_knowledge` / `skills` / `activity_log` / `all`로 검색 가능 (`reference/`는 대상 외) | 검색 불가 |
| Priming Channel C | 자동으로 조각이 표시됨 | 표시되지 않음 |
| `read_memory_file` | 읽기·쓰기 가능 | **읽기 전용** |
| 용도 | 일상의 실용 가이드·판단 기준 | 상세한 기술 참조 |
| 시스템 프롬프트 | 힌트 주입 있음 | 힌트 주입 있음 (별도 섹션) |