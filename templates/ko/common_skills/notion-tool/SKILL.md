---
name: notion-tool
description: >-
  Notion 연동 도구. 페이지·데이터베이스의 검색·조회·생성·업데이트를 API로 수행한다.
  Use when: Notion 페이지 편집, 데이터베이스 행 추가, 작업 공간의 검색·조회가 필요할 때.
tags: [productivity, notion, external]
---
Understood. Please provide the Japanese content you would like me to translate into Korean.# Notion 도구

Notion API를 통해 페이지·데이터베이스의 검색·조회·생성·업데이트를 수행하는 외부 도구.## 호출 방법

**Bash**: `animaworks-tool notion <サブコマンド> [引数]`에서 실행## 작업 목록### 검색 — 작업 공간 검색
```bash
animaworks-tool notion search [検索ワード] -j
```
### get_page — 페이지 메타데이터 가져오기
```bash
animaworks-tool notion get-page PAGE_ID -j
```
### get_page_content — 페이지 본문 가져오기
```bash
animaworks-tool notion get-page-content PAGE_ID -j
```
### get_database — 데이터베이스 메타데이터 가져오기
```bash
animaworks-tool notion get-database DATABASE_ID -j
```
### query — 데이터베이스 쿼리
```bash
animaworks-tool notion query DATABASE_ID [--filter JSON] [--sorts JSON] [-n 10] -j
```
- `filter`: Notion API 필터 JSON (선택)
- `sorts`: 정렬 조건 배열 (선택)### create_page — 페이지 생성
```bash
animaworks-tool notion create-page --parent-page-id ID --properties JSON -j
```
- `parent_page_id` 또는 `parent_database_id` 중 하나가 필수
- `children`: 페이지 본문 블록 배열 (선택)### update_page — 페이지 업데이트
```bash
animaworks-tool notion update-page PAGE_ID --properties JSON -j
```
### create_database — 데이터베이스 생성
```bash
animaworks-tool notion create-database --parent-page-id ID --title "名前" --properties JSON -j
```
## CLI 사용법

```bash
animaworks-tool notion search [検索ワード] -j
animaworks-tool notion get-page PAGE_ID -j
animaworks-tool notion get-page-content PAGE_ID -j
animaworks-tool notion get-database DATABASE_ID -j
animaworks-tool notion query DATABASE_ID [--filter JSON] [--sorts JSON] [-n 10] -j
animaworks-tool notion create-page --parent-page-id ID --properties JSON -j
animaworks-tool notion update-page PAGE_ID --properties JSON -j
animaworks-tool notion create-database --parent-page-id ID --title "名前" --properties JSON -j
```
## 주의사항

- Notion API Token은 credentials에 사전 설정이 필요함
- 페이지/데이터베이스의 ID는 하이픈 있음·없음 모두 가능
- properties의 구조는 Notion API의 스키마를 따름