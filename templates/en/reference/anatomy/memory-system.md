# Memory System Guide

A reference for how Anima's memory works, its types, and how to use them appropriately.
Use this to check how to search, write, and organize memories.

## Overview of Memory

Your memory consists of multiple types that correspond to the memory model of the human brain:

| Memory Type | Directory | Human Equivalent | Content |
|-----------|------------|------------|------|
| **Short-term memory** | `shortterm/` | Working memory | Context of recent conversations |
| **Episodic memory** | `episodes/` | Memory of experiences | What was done and when |
| **Semantic memory** | `knowledge/` | Knowledge | Things learned and know-how |
| **Procedural memory** | `procedures/` | Body-learned procedures | Step-by-step instructions on how to do things |
| **Skills** | `skills/` | Special talents and expertise | Executable procedure documents |

Additionally, there is memory shared across all Anima instances:

| Shared Memory | Path | Content |
|---------|------|------|
| **Shared knowledge** | `common_knowledge/` | Framework reference (including this file itself) |
| **Common skills** | `common_skills/` | Skills available to all Anima instances |
| **Organization shared knowledge** | `shared/common_knowledge/` | Knowledge accumulated by the organization during operations |
| **User profile** | `shared/users/` | Cross-Anima user information |

---

## Short-term Memory (shortterm/）

Holds **the context of recent conversations and sessions**. Equivalent to human working memory.

- Separated by session type via `shortterm/chat/` and `shortterm/heartbeat/` (with subdirectories per `thread_id` as needed)
- Each session-type directory contains `session_state.json` / `session_state.md` and `archive/` (completed or replaced entries are moved to `archive/`)
- When context window usage exceeds a threshold, older portions are automatically externalized
- For streaming execution, checkpoints recording tool completion positions (for reconnection and retry) are also managed at the same level
- Used to maintain context across sessions
- During daily housekeeping, archives related to short-term memory have a retention limit (adjustable via configuration)

You do not need to manipulate short-term memory directly. The framework manages it automatically.

---

## Episodic Memory (episodes/）

**Daily log of "what was done and when"**. Equivalent to human experiential memory.

- Automatically recorded in date-based files (e.g., `2026-03-09.md`). **Date-prefix plus suffix** patterns like `2026-03-09_topic.md` are also handled for splitting within the same day
- Consolidation's episode collection reads files matching the above pattern within a recent 24-hour window and splits entries by headings in the `## HH:MM — タイトル` format. Files without headings are treated as a single entry based on modification time (mtime)
- Used to recall "what was I doing last week" or "have I handled this issue before"
- Daily and weekly Consolidation (memory consolidation) performs summarization and knowledge extraction through Anima's own tool loop (described later)

### Writing Memories

```
write_memory_file(path="episodes/2026-03-09.md", content="...")
```

### Searching Memories

```
search_memory(query="Slack API接続テスト", scope="episodes")
```

---

## Semantic Memory (knowledge/）

**Learned knowledge, know-how, and patterns**. Equivalent to what humans "know".

- Lessons and patterns extracted from episodes
- Technical notes, response strategies, decision criteria
- Accumulated automatically through Consolidation, and can also be written actively by you
- Legacy-format files are migrated to YAML frontmatter format on first access (`knowledge/.migrated` marker)
- **Reconsolidation**: knowledge with frontmatter `failure_count >= 2` and `confidence < 0.6` can be revised by the LLM, just like procedures (knowledge path `ReconsolidationEngine`)

Examples:
- "Slack API rate limit is 1req/sec」 for Tier 1"
- "This client tends to contact us frequently on Mondays"
- "Pre-deployment checklist"

### Writing Memories

```
write_memory_file(path="knowledge/slack-api-notes.md", content="...")
```

### Searching Memories

```
search_memory(query="Slack API レート制限", scope="knowledge")
```

---

## Procedural Memory (procedures/）

**Step-by-step procedure documents for "how to do things"**. Equivalent to "body-learned procedures" in humans.

- Problem-solving procedures, routine workflow steps
- May be automatically generated from events such as `issue_resolved` (with metadata like confidence 0.4)
- **Not as fully protected as skills**: can be subject to the forgetting pipeline based on metadata (see the procedure-specific rules below)
- **Reconsolidation**: when frontmatter has **`failure_count >= 2` and `confidence < 0.6`**, the LLM revises the procedure document. After revision, the counter is reset, the version number is updated, and the old version is moved to `archive/` (implementation: `ReconsolidationEngine`)
- Version history remains in `archive/`, and old versions are pruned once they exceed a certain count (linked to the forgetting engine's procedure archive retention limit)

Examples:
- "SSL certificate renewal procedure"
- "New Anima onboarding procedure"
- "Production incident escalation procedure"

### Writing Memories

```
write_memory_file(path="procedures/ssl-renewal.md", content="...")
```

### Searching Memories

```
search_memory(query="SSL証明書 更新", scope="procedures")
```

---

## Skills (skills/）

**Executable procedure documents and tool usage guides**. Equivalent to "special talents".

- Includes personal skills (`skills/`) and common skills (`common_skills/`)
- Required skills are read via active skill context, Skill Router, Skill Hub, or `read_memory_file(path="...")`
- You do not need to read the full skill body every time. First look at the name, description, and pointers; read the body only when needed
- Proven `procedures/` may be promoted as probation skills or quarantine skills
- **Always exempt from forgetting in the vector store** (`skills` / `shared_users` types are protected)

### Checking Skills

```
read_memory_file(path="skills/newstaff/SKILL.md")  # スキルの全文を取得
```

### Creating Skills

```
create_skill(skill_name="deploy-procedure", description="本番デプロイ手順", body="...")
```

---

## Automatic Memory Processes

Compact automatic recall includes sender information, incomplete tasks, explicitly stated resident pointers, recent send history, and human-facing unread notifications. It searches relevant knowledge for conversation and task requests or questions, and retrieves recent activity and episodes within shared limits for heartbeat, cron, and inbox triggers. Broad graph expansion is not injected automatically; use explicit search when needed. `priming.max_tokens` defaults to 2,000, with notifications and mandatory resident rules held separately.

Search when past instructions, customer information, or ongoing work is needed. There is no need to search ritualistically for every response or report success after each use. Skill and procedure bodies are read when needed. Only explicitly stated memories are auto-resident; `[IMPORTANT]` alone does not designate residency.

For actions with side effects, `[ACTION-RULE]`, permissions, approvals, and duplicate execution prevention continue to apply. If shutdown has occurred, read the specified rules. Untrusted search results are separated from trusted context.

Daily consolidation only generates episodes and does not rewrite knowledge (except for project archive consolidation). Activity source records and memory originals are retained. Weekly and monthly changes, distillation, deactivation, self-correction, automatic skill learning, and automatic fact generation are also disabled by default. Indexing, repair, and reading of existing facts are maintained. Optional maintenance preserves customer-specific details, sources, and safety rules. Skipping or making no changes is normal and is not a reason for retry.

Curator promotion and retirement are proposals only by default. Safety blocks can be isolated immediately, and operator manual operations are also possible. Usage result counts are diagnostic material and do not prove work quality.

---

## Choosing Between Memory Tools

| What you want to do | Tool | Example |
|------------|--------|-----|
| Search memories by keyword | `search_memory` | `search_memory(query="API設定", scope="all")` |
| Read a specific file | `read_memory_file` | `read_memory_file(path="knowledge/api-notes.md")` |
| Write a memory | `write_memory_file` | `write_memory_file(path="knowledge/new-insight.md", content="...")` |
| Organize unneeded memories | `archive_memory_file` | `archive_memory_file(path="knowledge/outdated.md")` |

### Choosing a scope (search range)

| scope | Search target | When to use |
|-------|---------|----------|
| `knowledge` | Knowledge and know-how | "Do I know anything about this?" |
| `episodes` | Past activity logs | "Have I done this before?" |
| `procedures` | Procedure documents | "What are the steps for this task?" |
| `common_knowledge` | Shared references | "What are the framework specifications?" |
| `skills` | Skills and common skills (vector search) | "What skills can I use for this task?" |
| `activity_log` | Recent activity logs (tool results, messages, etc.) | "Content of the email I just read" or "the search results from earlier" |
| `all` | All of the above (vector search + activity_log BM25 integrated via RRF) | When you want to search broadly |

---

## How RAG (Vector Search) Works

RAG (Retrieval-Augmented Generation) is used for memory search:

1. **Indexing**: `knowledge/`, `episodes/`, `procedures/`, and shared `common_knowledge/` are chunked and stored in a vector store (default: Chroma, in a per-Anima persistent directory) via embeddings. File hashes are kept in `index_meta.json`, and **only changed files** are updated incrementally.
2. **Separate conversation summary collection**: Reads **`compressed_summary`** from `state/conversation.json`, chunks by **`### `** headings, and places them in a **dedicated collection** (`memory_type: conversation_summary` / metadata `source: conversation_gist`). This is separate from the normal knowledge index, allowing compressed notes from long chats to be included in search results.
3. **`.ragignore`**: Writing glob-style patterns in `.ragignore` directly under the data directory (`~/.animaworks/`) excludes matching paths from indexing (comment lines `#` allowed).
4. **Embedding model**: `rag.embedding_model` in `config.json` (default when unset: `intfloat/multilingual-e5-small`). The vector DB (ChromaDB) is owned by each Anima's root process; other processes deliver to root via the server's internal API (`/api/internal/vector`). Embedding and reranking are computed in one place on the server.
5. **Search**: The query is vectorized and ranked by combining similarity with **time decay** and reference frequency. The lower bound for results can be set via `rag.min_retrieval_score` in `config.json`. The same lower bound is applied for Priming and tool-based searches.
6. **Graph diffusion**: `rag.enable_spreading_activation` (default true) and `rag.spreading_memory_types` in `config.json` control **spreading activation** via the knowledge graph.
7. **Incremental updates and rebuilds**: In addition to re-indexing on file changes, **index rebuilds** run after daily, weekly, and monthly lifecycles to maintain consistency. If RAG inconsistency is detected, repair can isolate `vectordb` and rebuild.

RAG is used automatically when `search_memory` is called. You do not need to be aware of the mechanism, but
**tips for improving search accuracy**:
- Use queries with specific keywords
- When writing memories, make titles and content clear (file names affect keyword priority in Priming)
- Group related information into the same file
