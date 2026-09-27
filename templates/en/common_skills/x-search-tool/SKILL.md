---
name: x-search-tool
description: >-
  X (Twitter) search tool. Performs keyword searches and retrieves tweets from specified users.
  Use when: Use when: you need to search topics on X, retrieve posts from specific accounts, or understand trends and public opinion.
tags: [search, x, twitter, external]
---
Understood. I’m ready to translate the Japanese content into natural English while preserving all Markdown structure, headings, tables, links, identifiers, sentinels (including ⟦§number⟧ markers), and YAML frontmatter keys. I’ll keep the literal prefix “Use when:” unchanged and translate only the exposed values in the frontmatter. Please provide the content you’d like me to translate.# X Search Tool

An external tool for searching X (Twitter) and retrieving tweets.## How to Invoke

**Bash**: Run with `animaworks-tool x_search "検索クエリ" [オプション]` or `animaworks-tool x_search --user @username`### Search — Keyword Search
```bash
animaworks-tool x_search "検索クエリ" [-n 10] [--days 7]
```
### user_tweets — Fetch user tweets
```bash
animaworks-tool x_search --user @username [-n 10]
```
## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| query | string | — | Search query |
| user | string | — | Username (with @) |
| count | integer | 10 | Number of results to retrieve |
| days | integer | 7 | Number of days to search |## CLI Usage

```bash
animaworks-tool x_search "検索クエリ" [-n 10] [--days 7]
animaworks-tool x_search --user @username [-n 10]
```
## Notes

- X API (Bearer Token) configuration is required
- Search results are treated as external sources (untrusted)