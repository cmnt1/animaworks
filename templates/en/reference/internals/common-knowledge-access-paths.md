# common_knowledge reference paths

The five paths by which Anima accesses common_knowledge, and the mechanism of background RAG index construction.

---

## Overview of reference paths

| # | Path | Type | Anima's awareness |
|---|------|--------|------------|
| 1 | System prompt hint | Automatic | Actively accesses after seeing the hint |
| 2 | Priming Channel C | Automatic | Automatically displayed as related knowledge |
| 3 | `search_memory` tool | Active | Explicit search with scope specification |
| 4 | `read_memory_file` / `write_memory_file` | Active | Direct access with path specification |
| 5 | Claude Code direct file I/O (Mode S) | Active | Direct access via Read/Write etc. |

---

## Path 1: Hint injection into the system prompt

When `builder.py` builds the system prompt, if a file exists at `~/.animaworks/common_knowledge/`, it injects **hint text** into Group 4 (memory and abilities).

- **Injection timing**: At prompt construction (automatic)
- **Content**: Hints about the existence and usage of common_knowledge (does not include file contents)
- **Exclusion condition**: Omitted in the case of `is_task=True` (TaskExec)
- **Anima's behavior**: Actively accesses via `search_memory` or `read_memory_file` after seeing the hint

## Path 2: Priming Channel C / C0 — RAG vector search

`PrimingEngine` automatically performs a vector search based on message keywords, merges personal knowledge and shared common_knowledge, and injects the results into the system prompt.

- **Channel C budget**: 1200 tokens
- **Channel C0 budget**: 300 tokens (exclusively for overview pointers of chunks tagged with `[IMPORTANT]`)
- **Search target**: `shared_common_knowledge` collection (ChromaDB)
- **Merge method**: Merges and sorts with personal knowledge search results by score
- **Trust separation**: Channel C results are separated by trust level (medium / untrusted). Chunks originating from external platforms are treated as untrusted
- **Anima's behavior**: Relevant fragments of common_knowledge are automatically displayed in the Priming section

### Notes
- Due to the 1200-token constraint, only relevant fragments are shown, not the full text
- As the number of documents in common_knowledge grows, there is a risk that personal knowledge chunks get pushed out
- `[IMPORTANT]` chunks are always injected via Channel C0, making them effective for reliably recalling important business rules

## Path 3: `search_memory` tool

When Anima calls `search_memory(query="...", scope="common_knowledge")`, it searches common_knowledge using a hybrid of keyword search and vector search.

- **Keyword search**: Text scan of .md files within `~/.animaworks/common_knowledge/`
- **Vector search**: Searches the `shared_common_knowledge` collection
- **Scope specification**: `knowledge` / `episodes` / `procedures` / `common_knowledge` / `skills` / `activity_log` / `all`. Restricted search with `"common_knowledge"`, also included with `"all"` (default)
- **`scope="all"`**: In addition to the various vector search collections, **integrates BM25 results from activity_log via RRF (Reciprocal Rank Fusion)**. Recent action logs also appear as candidates during broad searches

### Usage example
```
search_memory(query="メッセージ 送信", scope="common_knowledge")
search_memory(query="レート制限", scope="all")
```

## Path 4: `read_memory_file` / `write_memory_file`

When Anima calls `read_memory_file(path="common_knowledge/...")`, it detects the path prefix and resolves it to `~/.animaworks/common_knowledge/`.

- **Read**: Accessible to all Anima instances
- **Write**: Accessible to all Anima instances (for accumulating shared knowledge)
- **Path traversal defense**: `is_relative_to` check prevents access outside common_knowledge

### Usage example
```
read_memory_file(path="common_knowledge/00_index.md")
write_memory_file(path="common_knowledge/operations/new-guide.md", content="...")
```

## Path 5: Claude Code direct file I/O (Mode S only)

In Mode S, Anima can directly access `~/.animaworks/common_knowledge/` using Claude Code's built-in tools (Read, Write, Grep, Glob, etc.).

- **Permission**: Allowed as a shared read-only directory via `handler_perms.py`
- **Target mode**: Mode S (Agent SDK) only

---

## Background: RAG index construction

For common_knowledge to be found via vector search (paths 2 and 3), it must be indexed in ChromaDB.

### Index timing

1. **At Anima startup**: When `MemoryManager` is initialized, `_ensure_shared_knowledge_indexed()` is called, detecting changes via SHA-256 hash. If changes exist, re-indexing is performed into the `shared_common_knowledge` collection
2. **Daily at 04:00**: `_run_daily_indexing()` performs incremental index updates on all Anima vector DBs. common_knowledge is also re-indexed at this timing

### Chunking strategy

In the case of `memory_type="common_knowledge"`, chunking is performed using the same **Markdown heading delimiters** as knowledge.

### Collection name

`shared_common_knowledge` (a single collection shared by all Anima instances)

---

## Differences from reference/

| Item | common_knowledge | reference |
|------|-----------------|-----------|
| RAG index | Targeted (`shared_common_knowledge`) | **Not targeted** |
| `search_memory` | Searchable via `knowledge` / `episodes` / `procedures` / `common_knowledge` / `skills` / `activity_log` / `all` (`reference/` is excluded) | Not searchable |
| Priming Channel C | Fragments displayed automatically | Not displayed |
| `read_memory_file` | Readable and writable | **Read-only** |
| Use | Everyday practical guides and decision criteria | Detailed technical reference |
| System prompt | Hint injection present | Hint injection present (separate section) |
