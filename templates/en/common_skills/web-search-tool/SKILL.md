---
name: web-search-tool
description: >-
  Web search tool. Searches for information on the internet using the Brave Search API.
  Use when: Use when: you need to research the latest news, search technical documentation, verify facts, or retrieve a list of search results.
tags: [search, web, external]
---
Understood. I’m ready to translate the Japanese content into natural English while preserving all Markdown structure, headings, tables, links, identifiers, sentinels (including ⟦§number⟧ markers), and YAML frontmatter keys. I’ll keep the literal prefix “Use when:” unchanged and return only the translation.

Please provide the Japanese content you’d like me to translate.# Web Search Tool

An external web search tool that uses the Brave Search API.## How to Call

**Bash**: Run with `animaworks-tool web_search "検索クエリ" [オプション]`## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| query | string | (required) | Search query |
| count | integer | 10 | Number of results |
| lang | string | "ja" | Search language |
| freshness | string | null | Freshness filter (pd=24h, pw=1 week, pm=1 month, py=1 year) |## CLI Usage

```bash
animaworks-tool web_search "検索クエリ" [-n 10] [-l ja] [-f pd]
```
## Notes

- BRAVE_API_KEY configuration is required
- Search results are treated as external sources (untrusted)