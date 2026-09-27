---
name: web-search-tool
description: >-
  웹 검색 도구. Brave Search API로 인터넷상의 정보를 검색한다.
  Use when: 최신 뉴스 조사, 기술 문서 검색, 사실 확인, 검색 결과 목록 확보가 필요할 때.
tags: [search, web, external]
---
Understood. Please provide the Japanese content you would like me to translate into Korean. I will follow all the specified rules: translating only the exposed values, preserving Markdown structure, sentinels, and the literal prefix 'Use when:' unchanged.# Web Search 도구

Brave Search API를 사용한 웹 검색 외부 도구.## 호출 방법

**Bash**: `animaworks-tool web_search "検索クエリ" [オプション]`에서 실행## 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|-----|-----------|------|
| query | string | (필수) | 검색 쿼리 |
| count | integer | 10 | 취득 건수 |
| lang | string | "ja" | 검색 언어 |
| freshness | string | null | 신선도 필터 (pd=24h, pw=1주, pm=1개월, py=1년) |## CLI 사용법

```bash
animaworks-tool web_search "検索クエリ" [-n 10] [-l ja] [-f pd]
```
## 주의사항

- BRAVE_API_KEY 설정이 필요함
- 검색 결과는 외부 소스(untrusted)로 취급됨