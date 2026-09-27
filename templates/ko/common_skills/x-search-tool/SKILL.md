---
name: x-search-tool
description: >-
  X（Twitter）검색 도구. 키워드 검색과 지정 사용자의 트윗 가져오기를 수행합니다.
  Use when: X에서의 화제 검색, 특정 계정의 게시물 가져오기, 트렌드·여론 파악이 필요할 때.
tags: [search, x, twitter, external]
---
Understood. Please provide the Japanese content you would like me to translate into Korean.# X Search 도구

X (Twitter)의 검색・트윗 획득을 수행하는 외부 도구.## 호출 방법

**Bash**: `animaworks-tool x_search "検索クエリ" [オプション]` 또는 `animaworks-tool x_search --user @username`로 실행### 검색 — 키워드 검색
```bash
animaworks-tool x_search "検索クエリ" [-n 10] [--days 7]
```
### user_tweets — 사용자 트윗 가져오기
```bash
animaworks-tool x_search --user @username [-n 10]
```
## 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|-----|-----------|------|
| query | string | — | 검색 쿼리 |
| user | string | — | 사용자 이름(@ 포함) |
| count | integer | 10 | 가져올 개수 |
| days | integer | 7 | 검색 대상 일수 |## CLI 사용법

```bash
animaworks-tool x_search "検索クエリ" [-n 10] [--days 7]
animaworks-tool x_search --user @username [-n 10]
```
## 주의사항

- X API (Bearer Token) 설정 필요
- 검색 결과는 외부 소스(untrusted)로 취급됨