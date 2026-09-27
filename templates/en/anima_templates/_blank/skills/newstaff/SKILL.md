---
name: newstaff
description: >-
  A skill for hiring or creating a new Digital Anima within the AnimaWorks organization.
  Based on the interview, create a character sheet (Markdown) and use the CLI command (animaworks anima create) to
  identity/injection/permissionsgenerate everything at once. After creation, self-maintain via bootstrap.
  "Create a new employee," "Hire someone," "New employee," "Hiring," "Create Anima," "Recruitment," "Add team members," "Add personnel," "Create a subordinate," "Add staff," "hire," "recruit," "team member"
---
Understood. I’m ready to translate the Japanese content into natural English while preserving all Markdown structure, headings, tables, links, identifiers, sentinels (including ⟦§number⟧ markers), and YAML frontmatter keys. I’ll keep the prefix “Use when:” unchanged and translate only exposed values in the frontmatter. Please provide the content to translate.# Skill: New Employee Hiring## Prerequisites

- The direction of the role for the employee to be created has been determined (if unclear, conduct an interview)## Procedure### 1. Interview (minimal is fine)

Gather the following information from the requester. **Only the bold items are required**; anything else unspecified will be auto-generated:

**Required:**
- **English name** (lowercase alphanumeric only. This becomes the directory name)
- **Role / area of expertise**: What they will handle (e.g., research, development, communication, infrastructure monitoring)
- **Personality direction**: Not the function but the tone (e.g., energetic, gal, airheaded, passionate, ojou, older sister). If there are already 2 cool types in the organization, don't choose that
- **Face type**: Choose one from `{data_dir}/prompts/face_types.md`. Avoid too much overlap with existing members

**Optional (use if specified, otherwise auto-generate):**
- Japanese name
- Age
- Any other preferences

**Technical configuration (use defaults if not specified):**
- Role: `commander` (can delegate to other employees) or `worker` (receives delegation)
- supervisor: English name of the Anima that is the supervisor (required for worker; if unspecified, use self)

**Brain (LLM model) configuration:**

Present the following table and let them choose:

| Level | Execution mode | Example models | Features | credential |
|--------|-----------|-------------|------|------------|
| S | autonomous | `claude-opus-4-6`, `claude-sonnet-4-6` | Claude Agent SDK. Most capable | anthropic |
| A | autonomous | `openai/gpt-4.1`, `google/gemini-2.5-pro`, `vertex_ai/gemini-2.5-flash` | Via LiteLLM. Tool use available | openai / google / azure / vertex |
| B | assisted | `ollama/gemma3:27b`, `ollama/qwen2.5-coder:32b` | No tools. Local execution, low cost | ollama |

※ If not specified, use the default (claude-sonnet-4 / autonomous / anthropic).### 2. Character Design (Auto-Generated)

Flesh out the character based on the information gathered from the interview. **Personality comes first, function follows.**

Always Read the following in this order:
1. `{data_dir}/prompts/face_types.md`
2. `{data_dir}/prompts/character_design_guide.md`

Do not associate a cool beauty with the role. Do not make hobbies an extension of work. Check that the hair color, face type, and speech style do not overlap with existing members.### 3. Create character sheets and batch-create via CLI

Write character sheets to files based on the **character sheet specification** from the interview and design results, then create them using CLI commands:

1. Write the character sheet to a file (e.g., `/tmp/{english_name}.md`)
2. Run the following command:

```bash
animaworks anima create --from-md /tmp/{english_name}.md --name {english_name} --supervisor {supervisor_english_name}
```

**supervisor configuration:**
- Explicitly specify via the `supervisor` parameter (recommended)
- If omitted: retrieve from the `| 上司 |` field of the character sheet
- If neither exists: the caller (Anima) becomes the supervisor

**Character sheet specification:**

```markdown
# キャラクターシート: {Japanese name}

## 基本情報

| 項目 | 設定 |
|------|------|
| 英名 | {lowercase alphanumeric} |
| 日本語名 | {Japanese full name} |
| 役職/専門 | {Role description} |
| 上司 | {supervisor English name} |
| 役割 | {commander / worker} |
| 実行モード | {autonomous / assisted} |
| モデル | {model name} |
| credential | {anthropic / openai / google / ollama} |

## 人格 (→ identity.md)

{Personality, speaking style, values, backstory, appearance, etc.}

## 役割・行動方針 (→ injection.md)

{Responsible areas, decision criteria, reporting rules, conduct standards, etc.}

## 権限 (→ permissions.json) [省略可]

{If omitted: default template applied}

## 定期業務 (→ heartbeat.md, cron.md) [省略可]

{If omitted: generic template applied. New Anima self-adjusts in bootstrap}

## 初回起動指示 (→ bootstrap.md 追加指示) [省略可]

{If omitted: standard bootstrap only}
```

**Required sections**: Basic information, personality, role and action policy
**Optional sections**: Permission, periodic tasks, initial startup instruction

This automatically executes the following:
- Batch creation of the directory structure
- Placement of skeleton files
- Placement of bootstrap.md
- Creation of status.json (including supervisor)
- Registration in config.json (model, supervisor, etc.)
- Application of defaults to omitted sections### 4. Check the model configuration for config.json

`animaworks anima create` will automatically register in config.json, but confirm and complete the following:

- `model`: Model name determined during the interview
- `credential`: Credential name to use
- `execution_mode`: autonomous or assisted
- `speciality`: Job title / specialty### 4.5. Heartbeat Frequency Proposal and Configuration

Based on the new employee's work driving style, propose a regular heartbeat interval to the requester and configure the agreed value:

| Driving Style | Recommended Interval | Example |
|--------|---------|-----|
| Self-directed situation assessment and adjustment as primary work | 30 minutes (default) | Team coordinator, progress supervisor |
| Message/event-driven as primary | 60–120 minutes | Review lead, development lead |
| Cron-based scheduled work as primary | 120–240 minutes | Monitoring, accounting, legal |

Add `"heartbeat_interval_minutes": <分>` (1–1440) to `{data_dir}/animas/{英名}/status.json` in the configuration.
Message-triggered heartbeats and cron operate independently of this setting, so extending the interval does not reduce responsiveness. When in doubt, choose a longer interval (wasted heartbeats consume tokens unnecessarily).### 5. Reflecting on the Server

```
Bash: curl -s -X POST http://localhost:18500/api/system/reload
```
### 6. Report to the Requester

Report the completion of the hire:
- The new employee's name and role
- The configured tech stack (model, execution mode)

⚠️ Do not report avatar image generation (the new Anima itself generates it via bootstrap)### From here on, the new Anima itself executes autonomously:
- Enhancement of identity.md / injection.md
- Self-design of heartbeat.md / cron.md
- Generation of avatar images (with supervisor reference)
- Arrival report to the supervisor