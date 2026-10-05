# 기억 시스템 가이드

Anima의 기억 구조·종류·용도별 사용법에 대한 참조.
기억의 검색·기록·정리 방법을 확인하기 위해 참조할 것.

## 기억의 전체 구조

당신의 기억은 인간의 뇌 기억 모델에 대응하는 여러 종류로 구성된다:

| 기억 종류 | 디렉터리 | 인간으로 치면 | 내용 |
|-----------|------------|------------|------|
| **단기 기억** | `shortterm/` | 작업 기억 | 최근 대화의 맥락 |
| **에피소드 기억** | `episodes/` | 경험의 기억 | 언제 무엇을 했는지 |
| **의미 기억** | `knowledge/` | 지식 | 배운 것·노하우 |
| **절차 기억** | `procedures/` | 몸이 기억한 절차 | 어떻게 하는지의 단계 |
| **스킬** | `skills/` | 특기·전문 기술 | 실행 가능한 절차서 |

또한, 모든 Anima가 공유하는 기억도 있다:

| 공유 기억 | 경로 | 내용 |
|---------|------|------|
| **공유 지식** | `common_knowledge/` | 프레임워크의 참조 (이 파일 자체도 포함) |
| **공통 스킬** | `common_skills/` | 모든 Anima가 사용할 수 있는 스킬 |
| **조직 공유 지식** | `shared/common_knowledge/` | 조직이 운영 중에 축적한 지식 |
| **사용자 프로필** | `shared/users/` | Anima 공통의 사용자 정보 |

---

## 단기 기억 (shortterm/）

**최근 대화나 세션의 맥락**을 유지한다. 인간의 작업 기억에 해당한다.

- `shortterm/chat/` 과 `shortterm/heartbeat/` 로 세션 유형별로 분리 (필요에 따라 `thread_id` 별 하위 디렉터리)
- 각 세션 유형 디렉터리에 `session_state.json` / `session_state.md` 와 `archive/` 가 있다 (완료·교체된 상태는 `archive/` 으로)
- 컨텍스트 창 사용률이 임계값을 초과하면 오래된 부분이 자동으로 외부화된다
- 스트리밍 실행을 위해 도구 완료 위치 등을 기록하는 체크포인트 (재연결·재시도용)도 같은 계층에서 관리된다
- 세션 간 맥락 연속에 사용된다
- 일일 하우스키핑에서 단기 기억 관련 아카이브에는 보관 일수 상한이 있다 (설정으로 조정 가능)

단기 기억은 직접 조작할 필요가 없다. 프레임워크가 자동 관리한다.

---

## 에피소드 기억 (episodes/）

**'언제 무엇을 했는지'의 일일 로그**. 인간의 경험 기억에 해당한다.

- 날짜별 파일 (예: `2026-03-09.md`)에 자동 기록된다. 같은 날 분할용으로 `2026-03-09_topic.md` 같은 **날짜 접두사＋접미사** 도 다룬다
- 통합 작업(Consolidation)의 에피소드 수집은 최근 24시간 창에서 위 패턴의 파일을 읽고, `## HH:MM — タイトル` 형식의 제목으로 항목을 분할한다. 제목이 없는 파일은 수정 시간(mtime)으로 1개 항목으로 처리한다
- '지난주에 무엇을 했는지' '이 문제를 이전에 처리했는지'를 떠올리기 위해 사용한다
- 일일·주간 Consolidation (기억 통합)에서는 Anima 자신의 도구 루프로 요약·지식 추출 등이 수행된다 (후술)

### 기억의 기록

```
write_memory_file(path="episodes/2026-03-09.md", content="...")
```

### 기억의 검색

```
search_memory(query="Slack API接続テスト", scope="episodes")
```

---

## 의미 기억 (knowledge/）

**배운 지식·노하우·패턴**. 인간의 '아는 것'에 해당한다.

- 에피소드에서 추출된 교훈이나 패턴
- 기술 메모, 대응 방침, 판단 기준
- Consolidation으로 자동 축적되는 외에 스스로 능동적으로 기록할 수 있다
- 레거시 형식의 파일은 첫 번째에 YAML 프론트매터가 있는 형식으로 이전된다 (`knowledge/.migrated` 마커)
- **재고정화**: 프론트매터에서 `failure_count >= 2` 이고 `confidence < 0.6` 인 knowledge는 절차와 마찬가지로 LLM에 의한 개정 대상이 될 수 있다 (`ReconsolidationEngine` 의 knowledge 경로)

예:
- 'Slack API의 속도 제한은 Tier 1에서 1req/sec」
- '이 클라이언트는 월요일에 연락이 많다'
- '배포 전 확인 항목 목록'

### 기억의 기록

```
write_memory_file(path="knowledge/slack-api-notes.md", content="...")
```

### 기억의 검색

```
search_memory(query="Slack API レート制限", scope="knowledge")
```

---

## 절차 기억 (procedures/）

**'어떻게 하는지'의 단계별 절차서**. 인간의 '몸이 기억한 절차'에 해당한다.

- 문제 해결 절차, 정형 작업의 흐름
- `issue_resolved` 등의 이벤트에서 자동 생성되기도 한다 (confidence 0.4 등의 메타데이터 포함)
- **스킬만큼의 전면 보호는 없다**: 메타데이터에 기반해 망각 파이프라인의 대상이 될 수 있다 (후술의 절차 전용 규칙)
- **재고정화(reconsolidation)**: 프론트매터에서 **`failure_count >= 2` 이고 `confidence < 0.6`** 일 때, LLM에 의한 절차서 개정이 실행된다. 개정 후에는 카운터 리셋·버전 번호 업데이트·이전 버전을 `archive/` 에 보관한다 (구현: `ReconsolidationEngine`)
- 버전 이력은 `archive/` 에 남고, 오래된 버전은 일정 수를 초과하면 정리된다 (망각 엔진 쪽의 절차 아카이브 보관 개수와도 연동)

예:
- 'SSL 인증서 갱신 절차'
- '신규 Anima 온보딩 절차'
- '본방 장애 시 에스컬레이션 절차'

### 기억의 기록

```
write_memory_file(path="procedures/ssl-renewal.md", content="...")
```

### 기억의 검색

```
search_memory(query="SSL証明書 更新", scope="procedures")
```

---

## 스킬 (skills/）

**실행 가능한 절차서·도구 사용 가이드**. '특기'에 해당한다.

- 개인 스킬 (`skills/`)과 공통 스킬 (`common_skills/`)이 있다
- 필요한 스킬은 active skill context, Skill Router, Skill Hub, 또는 `read_memory_file(path="...")` 로 읽는다
- 스킬 본문을 항상 전부 읽을 필요는 없다. 먼저 이름·설명·포인터를 보고, 필요해졌을 때만 본문을 읽는다
- 실적이 있는 `procedures/` 은 probation skill이나 quarantine skill로 승격될 수 있다
- **벡터 스토어상에서는 항상 망각 대상 외** (`skills` / `shared_users` 형은 보호)

### 스킬의 확인

```
read_memory_file(path="skills/newstaff/SKILL.md")  # スキルの全文を取得
```

### 스킬의 생성

```
create_skill(skill_name="deploy-procedure", description="本番デプロイ手順", body="...")
```

---

## 기억의 자동 프로세스

compact의 자동 회상에는 발신자 정보, 미완료 작업, 명시적으로 지정된 상주 포인터, 최근 전송 기록, 사람에게 알려야 할 미알림 사항이 포함됩니다. 대화·작업 요청이나 질문에서는 관련 지식을 검색하고, heartbeat·cron·inbox에서는 공통 설정 상한 내에서 최근 활동이나 에피소드도 가져옵니다. 광범위한 그래프 확장은 자동 주입하지 않으며, 필요한 경우 명시적으로 검색합니다. `priming.max_tokens`은 기본값이 2,000이며, 알림과 필수 상주 규칙은 별도로 유지합니다.

과거 지침·고객 정보·진행 중인 작업이 필요한 경우 검색하세요. 모든 답변에서 의례적으로 검색하거나 사용할 때마다 성공을 보고할 필요는 없습니다. 스킬·절차의 본문은 필요할 때 읽습니다. 자동 상주하는 것은 명시된 기억뿐이며, `[IMPORTANT]`만으로는 상주 지정이 되지 않습니다.

부작용이 있는 행동에는 `[ACTION-RULE]`, 권한, 승인, 중복 실행 방지가 계속 적용됩니다. 종료된 경우 지정된 규칙을 읽으세요. 신뢰할 수 없는 검색 결과는 신뢰된 맥락과 분리됩니다.

일일 통합은 에피소드 생성만 수행하며, 지식을 다시 쓰지는 않습니다(프로젝트 아카이브 통합 제외). 활동 원기록과 기억 원본은 보존합니다. 주간·월간 변경, 증류, 저활성화, 자기 수정, 스킬 자동 학습, facts 자동 생성도 기본적으로 비활성화되어 있습니다. 인덱스·복구·기존 facts 읽기는 유지합니다. 선택적 유지보수에서도 고객별 세부 정보·출처·안전 규칙을 보존합니다. 건너뛰기·변경 없음은 정상이며, 재시도 사유가 되지 않습니다.

Curator의 승격·퇴역은 기본적으로 제안만 합니다. 안전상의 차단은 즉시 격리할 수 있으며, 운영자가 명시적으로 조작할 수도 있습니다. 사용 결과 건수는 진단 자료일 뿐, 작업의 품질을 입증하지 않습니다.

---

## 기억 도구의 용도별 사용

| 하고 싶은 일 | 도구 | 예 |
|------------|--------|-----|
| 키워드로 기억 찾기 | `search_memory` | `search_memory(query="API設定", scope="all")` |
| 특정 파일 읽기 | `read_memory_file` | `read_memory_file(path="knowledge/api-notes.md")` |
| 기억 기록하기 | `write_memory_file` | `write_memory_file(path="knowledge/new-insight.md", content="...")` |
| 불필요한 기억 정리하기 | `archive_memory_file` | `archive_memory_file(path="knowledge/outdated.md")` |

### scope (검색 범위) 선택 방법

| scope | 검색 대상 | 언제 사용하는가 |
|-------|---------|----------|
| `knowledge` | 지식·노하우 | '이것에 대해 뭔가 알고 있나?' |
| `episodes` | 과거 행동 로그 | '전에 이것을 한 적 있나?' |
| `procedures` | 절차서 | '이 작업의 절차는?' |
| `common_knowledge` | 공유 참조 | '프레임워크의 사양은?' |
| `skills` | 스킬·공통 스킬 (벡터 검색) | '이 작업에 사용할 수 있는 스킬은?' |
| `activity_log` | 최근 행동 로그 (도구 실행 결과·메시지 등) | '방금 읽은 메일의 내용' '아까의 검색 결과' |
| `all` | 위 전부 (벡터 검색 + activity_log BM25를 RRF로 통합) | 폭넓게 검색하고 싶은 경우 |

---

## RAG(벡터 검색)의 작동 방식

기억 검색에는 RAG(Retrieval-Augmented Generation)가 사용됩니다:

1. **인덱싱**: `knowledge/`·`episodes/`·`procedures/`·공유 `common_knowledge/` 등이 청크로 나뉘고, 임베딩을 통해 벡터 저장소(기본값은 Chroma, Anima별 영속 디렉터리)에 저장됩니다. 파일 해시를 `index_meta.json`에 보관하고, **변경된 파일만** 차이를 반영해 업데이트합니다.
2. **대화 요약용 별도 컬렉션**: `state/conversation.json`의 **`compressed_summary`**을 읽고, `### ` 제목 단위로 청크화하여 **전용 컬렉션**(`memory_type: conversation_summary` / 메타데이터 `source: conversation_gist`)에 넣습니다. 일반 지식 인덱스와는 별도로 관리되므로, 장기 채팅의 압축 메모도 검색 대상으로 포함할 수 있습니다.
3. **`.ragignore`**: 데이터 디렉터리(`~/.animaworks/`) 바로 아래의 `.ragignore`에 glob 형식의 패턴을 작성하면, 해당 경로는 인덱싱 대상에서 제외됩니다(주석 행 `#`도 사용 가능).
4. **임베딩 모델**: `config.json`의 `rag.embedding_model`(미설정 시 `intfloat/multilingual-e5-small`). 벡터 DB(ChromaDB)는 각 Anima의 root 프로세스가 소유하며, 다른 프로세스는 서버의 내부 API(`/api/internal/vector`)를 통해 root에 전달합니다. 임베딩과 rerank는 서버 한 곳에서 계산합니다.
5. **검색**: 벡터 검색과 BM25 키워드 검색을 병렬로 수행하고, RRF로 순위를 통합한 뒤 상위 후보를 cross-encoder로 재정렬합니다. `config.json`의 `rag.min_retrieval_score`에서 결과의 최솟값을 설정할 수 있습니다. Priming이나 도구를 통한 검색에도 같은 최솟값 설정이 적용됩니다.

6. **증분 업데이트와 재구축**: 파일 변경에 따른 재인덱싱뿐 아니라 일일·주간·월간 라이프사이클 이후에도 **인덱스 재구축**을 수행해 정합성을 맞춥니다. RAG 불일치가 감지되면 repair가 `vectordb`을 격리하고 재구축할 수 있습니다.

RAG는 `search_memory`을 호출하면 자동으로 사용됩니다. 작동 방식을 의식할 필요는 없지만,
**검색 정확도를 높이는 요령**:
- 구체적인 키워드가 포함된 쿼리를 사용합니다
- 기억을 작성할 때 제목과 내용을 명확히 합니다(파일 이름이 Priming의 키워드 우선순위에 영향을 줍니다)
- 관련 정보는 같은 파일에 모읍니다
