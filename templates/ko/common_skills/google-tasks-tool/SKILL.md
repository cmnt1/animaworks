---
name: google-tasks-tool
description: >-
  Google Tasks 연동 도구. 작업 목록과 작업의 조회·추가·업데이트를 OAuth2로 수행합니다.
  Use when: TODO 목록 조회, 작업 추가, 완료 업데이트, 작업 목록 전환이 필요할 때.
tags: [tasks, google, todo, external]
---


# Google Tasks 도구

Google Tasks API로 작업 목록·작업을 조작하는 외부 도구.

## 호출 방법

**Bash**: `animaworks-tool google_tasks <サブコマンド> [引数]`로 실행

## 액션 목록

### list_tasklists — 작업 목록 조회
```bash
animaworks-tool google_tasks tasklists [-n 50]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|-----|-----------|------|
| max_results | integer | 50 | 최대 조회 건수 |

### list_tasks — 작업 조회
```bash
animaworks-tool google_tasks list <タスクリストID> [-n 50] [--no-completed]
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|-----|------|------|
| tasklist_id | string | Yes | 작업 목록 ID |
| max_results | integer | 50 | 최대 조회 건수 |
| show_completed | boolean | true | 완료 작업 포함 여부 |

### insert_task — 작업 추가
```bash
animaworks-tool google_tasks add <タスクリストID> "タスク名" [--notes メモ] [--due 日時]
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|-----|------|------|
| tasklist_id | string | Yes | 작업 목록 ID |
| title | string | Yes | 작업 이름 |
| notes | string | No | 메모 |
| due | string | No | 마감일 (RFC 3339) |

### insert_tasklist — 작업 목록 생성
```bash
animaworks-tool google_tasks new-list "リスト名"
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|-----|------|------|
| title | string | Yes | 목록 이름 |

### update_task — 작업 업데이트
지정한 작업의 제목·메모·마감일·완료 상태를 업데이트합니다 (지정한 항목만 업데이트).

```bash
animaworks-tool google_tasks update <タスクリストID> <タスクID> [--title タイトル] [--notes メモ] [--due 日時] [--status completed|needsAction]
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|-----|------|------|
| tasklist_id | string | Yes | 작업 목록 ID |
| task_id | string | Yes | 작업 ID |
| title | string | No | 새 제목 |
| notes | string | No | 메모 |
| due | string | No | 마감일 (RFC 3339) |
| status | string | No | `needsAction` (미완료) 또는 `completed` (완료). title/notes/due/status 중 하나 이상을 지정해야 합니다. |

### update_tasklist — 작업 목록 이름 업데이트
```bash
animaworks-tool google_tasks update-list <タスクリストID> "新しいリスト名"
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|-----|------|------|
| tasklist_id | string | Yes | 작업 목록 ID |
| title | string | Yes | 새 목록 이름 |

## 주의사항

- 최초 사용 시 OAuth2 인증 흐름 필요
- credentials.json를 `~/.animaworks/credentials/google_tasks/`에 배치할 것 (Gmail/Calendar과 동일한 OAuth 클라이언트 복사 가능)
