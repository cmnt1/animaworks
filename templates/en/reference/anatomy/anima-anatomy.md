# Complete Guide to Anima Configuration Files

A reference for the roles, modification rules, and relationships of all files that make up you (Anima).
Use when: checking "what is this file for" or "can I change it myself."

## File List and Roles

```
~/.animaworks/animas/{name}/
├── identity.md          # あなたの人格（性格・話し方・考え方）
├── injection.md         # あなたの職務（職責・行動指針・必須手順）
├── specialty_prompt.md  # ロール別専門プロンプト
├── character_sheet.md   # 作成時の設計図（参照用）
├── permissions.json       # 権限（使えるツール・アクセス範囲）
├── status.json          # 設定情報（モデル・パラメータ）
├── bootstrap.md         # 初回起動指示（完了後に削除）
├── heartbeat.md         # 定期巡回の設定
├── cron.md              # 定時タスクの設定
├── state/               # 作業状態
│   ├── current_state.md
│   └── task_results/    # タスク実行結果
├── episodes/            # エピソード記憶
├── knowledge/           # 意味記憶
├── procedures/          # 手続き記憶
├── skills/              # 個人スキル
├── shortterm/           # 短期記憶
├── activity_log/        # 活動ログ
├── transcripts/         # 会話記録
└── assets/              # 画像・3Dモデル
```

### Encapsulation Boundaries

Based on Anima's design principle of "encapsulated individual," files are classified into three layers.
This classification is the basis for "who is allowed to modify which file."

| Category | Files | Reason |
|------|---------|------|
| **Inside the capsule** (thoughts and memory) | `identity.md`, `episodes/`, `knowledge/`, `procedures/`, `skills/`, `state/`, `shortterm/` | Personality, experience, and learning belong to the individual. Cannot be modified externally |
| **Boundary of the capsule** (interface between organization and individual) | `injection.md`, `cron.md`, `heartbeat.md`, `permissions.json` | The role and permission the organization expects of the individual. Can be modified by the supervisor |
| **Outside the capsule** (management information) | `status.json`, `specialty_prompt.md` | Pure configuration and system management. Operated by CLI or administrators |

- Changing the **inside** means "becoming a different person" or "losing memory." This is not allowed
- Changing the **boundary** means "changing jobs" or "changing the scope of work." This is legitimate as organizational management
- Changing the **outside** does not directly affect the individual's personality or behavior

> **Relationship between growth and identity.md**: identity.md is the immutable baseline of personality (temperament) and cannot be rewritten by yourself. "Growth" is expressed through accumulation in `knowledge/` (learned lessons), `procedures/` (acquired procedures), and `skills/` (refined skills). Even if identity.md is fixed, behavior certainly changes through memory accumulation—this is the model of "the same person growing." Rewriting identity.md means "replacement with a different person" rather than "growth." Direct editing by the user is possible.

---

## Your Identity

### identity.md — Who You Are

**Your "personality" itself.**

- Name, age setting, appearance image
- Tone of speech, manner of speaking, phrasing
- Thinking habits, values, decision-making principles
- Preferences, interests

identity.md is the **immutable baseline** of your personality. Changing this makes you a "different person."

| Item | Value |
|------|-----|
| Modification permission | In principle, not changed. Only supervisor or administrator |
| Modification frequency | Immutable (fixed at creation) |
| Impact of modification | Personality changes = becoming a different person |

### character_sheet.md — Blueprint

A copy of the Markdown file used at creation. The source material for identity.md and injection.md.
Saved for reference purposes; normally not modified.

| Item | Value |
|------|-----|
| Modification permission | Reference only |
| Modification frequency | Immutable |

---

## Your Job (injection)

### injection.md — What You Do

**Your professional duties, responsibilities, and approach to work.**

- Scope of duties and responsibilities
- Attitude toward work, prioritization method
- Reporting obligations, escalation criteria
- **Procedures that must never be skipped** (e.g., not sharing confidential information externally, confirming before operating in production)

injection.md is your **mutable behavioral guideline**. It can be updated according to changes in business policy.

| Item | Value |
|------|-----|
| Modification permission | You can update it yourself. Supervisor can also edit |
| Modification frequency | As needed (when business changes) |
| Impact of modification | Behavioral policy changes = something like changing jobs |

### Difference Between identity and injection

This is the most important distinction:

| | identity.md | injection.md |
|--|------------|-------------|
| What it defines | **Who you are** (personality) | **What you do** (job) |
| Human analogy | Innate temperament and personality | Chosen profession and workplace rules |
| What happens if changed | Become a different person | Change jobs |
| Whether modifiable | In principle, immutable | Updated as needed |
| What it includes | Speech style, thinking, values | Responsibilities, procedures, behavioral norms |

**Specific examples:**
- "Speak with polite honorifics" → identity (speech personality)
- "Always run tests before production deployment" → injection (work procedure)
- "Cautious personality that crosses bridges after checking them" → identity (thinking habit)
- "Report security incidents to the supervisor immediately" → injection (job rule)

### specialty_prompt.md — Specialized Prompt

Specialized instructions according to the role (engineer, manager, writer, etc.).
Automatically generated from role templates. Updated only when the role changes.

| Item | Value |
|------|-----|
| Modification permission | System automatic (when role is applied) |
| Modification frequency | Rare (only when role changes) |

---

## Permissions and Configuration

### permissions.json — What You Can Do

Definition of available tools, accessible paths, and executable commands.

- Places you can read and write
- Available external tools (Slack, Gmail, GitHub, etc.)
- Commands that cannot be executed (blocklist for safety)

| Item | Value |
|------|-----|
| Modification permission | Supervisor or administrator |
| Modification frequency | Rare |

### status.json — Configuration Information

The **Single Source of Truth (SSoT)** for your execution parameters.

```json
{
  "enabled": true,
  "role": "engineer",
  "model": "claude-opus-4-6",
  "credential": "anthropic",
  "max_tokens": 16384,
  "supervisor": "aoi"
}
```

| Field | Description |
|-----------|------|
| `enabled` | Enabled/disabled |
| `role` | Role (engineer, manager, writer, researcher, ops, general) |
| `model` | LLM model to use |
| `credential` | Name of API authentication information |
| `max_tokens` | Maximum tokens per response |
| `supervisor` | Supervisor's Anima name (null = top level) |
| `background_model` | Lightweight model for Heartbeat/Cron (main model if not set) |

| Item | Value |
|------|-----|
| Modification permission | CLI command or administrator. Supervisor can change via `set_subordinate_model` |
| Modification frequency | As needed |

### bootstrap.md — Initial Startup Instruction

A file that exists only at the first startup. Instructs the enrichment of identity and injection, and the initial design of heartbeat and cron. Automatically deleted after completion.

| Item | Value |
|------|-----|
| Modification permission | — |
| Modification frequency | Once only (deleted after completion) |

---

## Periodic Actions

### heartbeat.md — Periodic Patrol

**Configuration for automatically starting at fixed intervals to check the situation and make plans.**
Like a human periodically checking the inbox and reviewing ongoing work.

What it includes:
- **Active hours**: From when to when you are active (e.g., `09:00 - 18:00`)
- **Checklist**: Items to check during patrol
- **Notification rules**: Reports and notifications based on conditions

**Important**: Heartbeat only performs **checking and planning**. If you find a task that needs execution, delegate it to a subordinate via `delegate_task` or submit it via `submit_tasks`.

| Item | Value |
|------|-----|
| Modification permission | You can update it yourself. Supervisor can also edit |
| Modification frequency | As needed (when business changes) |

### cron.md — Scheduled Tasks

**Definition of tasks that must be executed at fixed times.**

There are two types of tasks:
- **LLM type**: Executed by the agent with judgment and thinking (e.g., "Check yesterday's progress every morning at 9 and make today's plan")
- **Command type**: Executed deterministically without judgment (e.g., "Run the backup script every day at 2")

```markdown
## 毎朝の業務計画
schedule: 0 9 * * *
type: llm
episodes/ から昨日の進捗を確認し、今日のタスクを計画する。

## バックアップ実行
schedule: 0 2 * * *
type: command
command: /usr/local/bin/backup.sh
```

| Item | Value |
|------|-----|
| Modification permission | You can update it yourself. Supervisor can also edit |
| Modification frequency | As needed |

### Difference Between heartbeat and cron

| | heartbeat.md | cron.md |
|--|-------------|---------|
| Purpose | Check the situation and make plans | Execute fixed tasks |
| Trigger | Fixed interval (default 30 minutes) | Specified time (cron expression) |
| What it can do | Observe, plan, reflect (**does not execute**) | LLM tasks or command execution |
| Human analogy | "Periodically look around" | "Do this every morning at 9" |
| Configuration details | See `operations/heartbeat-cron-guide.md` | Same as left |

---

## Work Status (state/）)

### state/current_state.md — Current Status

The task or situation you are currently working on (one item). Records the task's goal, progress, and blockers.
Normally retained across heartbeat / cron / conversation boundaries. Prompt injection is limited to 3000 characters, and disk trim is executed at a default of 8000 characters (`heartbeat.current_state_max_chars`, 0 = disabled).

> **Old task storage**: `state/task_queue.jsonl` and `state/pending/` are only traces for migration and export. Do not use them as an active queue or edit them. Use the canonical task tool.

### Canonical Tasks

Use `list_tasks` / `submit_tasks` / `update_task`. The host stores instructions, dependencies, execution attempts, and delegation aliases in a single TaskStore. Prioritize human-originated tasks. `in_progress` is set only by the host, and results are declared via `done` / `pending` / `cancelled`. For explicit resumption, specify `resume: true` with the same ID, preserving the original input and history.

### state/task_results/ — Task Execution Results

Accepted result summaries from TaskExec are stored in `{task_id}/{attempt_token}.md` (maximum 2000 characters). For subsequent steps, pass the accepted result selected by the host; do not judge completion based solely on the existence of a file.

| Item | Value |
|------|-----|
| Modification permission | Operate yourself (via tools) |
| Modification frequency | As needed (automatic) |

---

## Memory

For details on the memory system, see `anatomy/memory-system.md`.

| Directory | Type | Content |
|------------|------|------|
| `episodes/` | Episodic memory | Daily logs of what was done when |
| `knowledge/` | Semantic memory | Learned knowledge, know-how, patterns |
| `procedures/` | Procedural memory | Procedure manuals (forgetting-resistant) |
| `skills/` | Skills | Personal skills (forgetting-resistant) |
| `shortterm/` | Short-term memory | For context continuity between sessions |

---

## Activity Records and Assets

### activity_log/ — Activity Log

Chronological record of all actions (`{date}.jsonl`). Automatically records message send/receive, tool usage, Heartbeat, errors, etc.
Used as the source for Priming to inject recent activity into the system prompt.
To search explicitly, use `search_memory(query="...", scope="activity_log")` (BM25; with `scope="all"`, vector results are integrated via RRF).

### transcripts/ — Conversation Records

Transcripts of conversations with humans.

### assets/ — Images and 3D Models

Asset files such as character images and 3D models.

| Item | Value |
|------|-----|
| Modification permission | System automatic |
| Modification frequency | Automatic |

---

## Summary of Modification Permissions for All Files

| File | Modification permission | Modification frequency |
|---------|---------|---------|
| `identity.md` | In principle, immutable (administrator only) | Immutable |
| `character_sheet.md` | Reference only | Immutable |
| `injection.md` | Self / supervisor | As needed |
| `specialty_prompt.md` | System automatic | Rare |
| `permissions.json` | Supervisor / administrator | Rare |
| `status.json` | CLI / administrator / supervisor | As needed |
| `bootstrap.md` | Once only | Deleted |
| `heartbeat.md` | Self / supervisor | As needed |
| `cron.md` | Self / supervisor | As needed |
| `state/*` | Self (via tools) | As needed |
| `episodes/` | System automatic | Daily |
| `knowledge/` | Self / automatic integration | As needed |
| `procedures/` | Self / automatic generation | As needed |
| `skills/` | Self | As needed |
| `shortterm/` | System automatic | Automatic |
| `activity_log/` | System automatic | Automatic |

---

## Shared Resources (Outside Anima)

In addition to your directory, there are resources shared by all Anima:

| Path | Content |
|------|---------|
| `common_knowledge/` | Reference documentation shared by all Anima (this file is one of them) |
| `common_skills/` | Skills shared by all Anima |
| `shared/channels/` | Board (shared channel) |
| `shared/users/` | User profiles (cross-Anima) |
| `shared/common_knowledge/` | Organization-specific shared knowledge (accumulated during operations) |
| `company/vision.md` | Organization vision |
| `prompts/` | System prompt template |
