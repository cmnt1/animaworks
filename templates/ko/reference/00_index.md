# 참조 — 기술 참조 목차

AnimaWorks의 상세 기술 사양 및 관리자용 설정 가이드 목록.
RAG 검색 대상 외. 필요할 때 `read_memory_file(path="reference/...")`에서 직접 참조할 것.

## 참조 파일

### anatomy/ — 구성·아키텍처

| 파일 | 제목 |
|------|-------|
| `anatomy/anima-anatomy.md` | Anima 구성 파일 완전 가이드 |
| `anatomy/environment-layout.md` | 런타임 디렉터리 구성과 권한 |
| `anatomy/memory-system.md` | 기억 시스템 가이드 |
| `anatomy/priming-channels.md` | Priming 채널 기술 참조 |
| `anatomy/working-memory.md` | 작업 메모리(state/） 기술 참조 |

### communication/ — 메시징·연동

| 파일 | 제목 |
|------|-------|
| `communication/instruction-patterns.md` | 지침 전달 방법 패턴 모음 |
| `communication/messaging-guide.md` | 메시지 전송 완전 가이드 |
| `communication/reporting-guide.md` | 보고·에스컬레이션 방법 |
| `communication/slack-bot-token-guide.md` | Slack 봇 토큰 설정 가이드 |

### internals/ — 프레임워크 내부 사양

| 파일 | 제목 |
|------|-------|
| `internals/common-knowledge-access-paths.md` | common_knowledge 참조 경로 |

### operations/ — 관리·운영 설정

| 파일 | 제목 |
|------|-------|
| `operations/browser-automation-guide.md` | 브라우저 조작 가이드 |
| `operations/heartbeat-cron-guide.md` | 정기 실행 설정과 운영 |
| `operations/memory-writing-guide.md` | 기억 기록 위치와 정기 실행 선택 |
| `operations/mode-s-auth-guide.md` | Mode S(Agent SDK) 인증 모드 설정 가이드 |
| `operations/model-guide.md` | 모델 선택·설정 가이드 |
| `operations/project-setup.md` | 프로젝트 설정 방법 |
| `operations/task-management.md` | 작업 관리 방법 |
| `operations/tool-usage-overview.md` | 도구 사용 가이드 |
| `operations/voice-chat-guide.md` | 음성 채팅(Voice Chat) 가이드 |

### organization/ — 조직 구조

| 파일 | 제목 |
|------|-------|
| `organization/roles.md` | 역할과 책임 범위 |
| `organization/structure.md` | 조직 구조의 작동 방식 |

### troubleshooting/ — 트러블슈팅

| 파일 | 제목 |
|------|-------|
| `troubleshooting/common-issues.md` | 자주 발생하는 문제와 해결 방법 |
| `troubleshooting/escalation-flowchart.md` | 막혔을 때의 플로차트 |
| `troubleshooting/gmail-credential-setup.md` | Gmail Tool 인증 설정 가이드 |

### usecases/ — 사용 사례 가이드

| 파일 | 제목 |
|------|-------|
| `usecases/usecase-communication.md` | 사용 사례: 커뮤니케이션 자동화 |
| `usecases/usecase-customer-support.md` | 사용 사례: 고객 지원 |
| `usecases/usecase-development.md` | 사용 사례: 소프트웨어 개발 지원 |
| `usecases/usecase-knowledge.md` | 사용 사례: 지식 관리·문서 정비 |
| `usecases/usecase-monitoring.md` | 사용 사례: 인프라·서비스 모니터링 |
| `usecases/usecase-overview.md` | AnimaWorks 사용 사례 가이드 |
| `usecases/usecase-research.md` | 사용 사례: 조사·리서치·분석 |
| `usecases/usecase-secretary.md` | 사용 사례: 비서·사무 지원 |

## 관련 항목

- 일상 실용 가이드 → `common_knowledge/00_index.md`
- 공통 스킬 → `common_skills/`