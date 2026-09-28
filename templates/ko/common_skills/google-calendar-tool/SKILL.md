---
name: google-calendar-tool
description: >-
  Google 캘린더 연동 도구. 일정 목록 조회 및 생성을 OAuth2로 Calendar API를 통해 수행한다.
  Use when: 일정 확인, 새 이벤트 생성, 일정 변경, 캘린더 동기화가 필요할 때.
tags: [calendar, google, schedule, external]
---


# Google Calendar 도구

Google 캘린더의 이벤트를 OAuth2로 직접 조작하는 외부 도구.

## 호출 방법

**Bash**: `animaworks-tool google_calendar <サブコマンド> [引数]` 로 실행

## 액션 목록

### list — 일정 목록 조회
```bash
animaworks-tool google_calendar list [-n 20] [-d 7] [--calendar-id primary]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|-----|-----------|------|
| max_results | integer | 20 | 최대 조회 건수 |
| days | integer | 7 | 며칠 이후까지 조회할지 |
| calendar_id | string | "primary" | 캘린더 ID |

### add — 일정 추가
```bash
animaworks-tool google_calendar add "会議" --start 2026-03-04T10:00:00+09:00 --end 2026-03-04T11:00:00+09:00
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|-----|------|------|
| summary | string | Yes | 이벤트 제목 |
| start | string | Yes | 시작 시간 (ISO8601 또는 YYYY-MM-DD) |
| end | string | Yes | 종료 시간 (ISO8601 또는 YYYY-MM-DD) |
| description | string | No | 상세 설명 |
| location | string | No | 장소 |
| calendar_id | string | No | 캘린더 ID (기본값: primary) |
| attendees | array | No | 참석자 이메일 주소 목록 |

## CLI 사용법

```bash
animaworks-tool google_calendar list [-n 20] [-d 7] [--calendar-id primary]
animaworks-tool google_calendar add "会議" --start 2026-03-04T10:00:00+09:00 --end 2026-03-04T11:00:00+09:00
```

## 주의사항

- 최초 사용 시 OAuth2 인증 플로우 필요
- credentials.json 를 ~/.animaworks/credentials/google_calendar/ 에 배치할 것
- 종일 이벤트는 start/end 를 YYYY-MM-DD 형식으로 지정
