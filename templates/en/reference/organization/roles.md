# Roles and Responsibilities

In AnimaWorks, each Anima has different roles and responsibilities depending on their position in the hierarchy.
This document defines the role, responsibility, and expected behavior patterns for each level.

## Role Categories

An Anima's role is determined automatically by the `supervisor` field and whether they have subordinates:

| Condition | Role | Example |
|-----------|------|---------|
| supervisor = null, has subordinates | Top-level | CEO, representative |
| supervisor = null, no subordinates | Independent Anima | Solo specialist |
| Has supervisor, has subordinates | Mid-level management | Department head, team lead |
| Has supervisor, no subordinates | Worker | Developer, assignee |

## Top-Level Anima (supervisor = null)

Located at the top of the organization; responsible for overall direction and final decisions.

### Responsibilities

- Setting organization-wide goals and strategy
- Assigning work and determining priorities for subordinates
- Final approval on important decisions (technology selection, policy changes, external relations, etc.)
- Considering hiring new Anima (e.g. additions via `animaworks anima create`)
- Monitoring and improving organization-wide outcomes

### MUST (Required)

- MUST respond to escalations from subordinates
- MUST make decisions aligned with the organization's vision (`company/vision.md`)
- MUST mediate conflicts and resolve blockers between subordinates

### SHOULD (Recommended)

- SHOULD regularly check subordinate work status (e.g. via Heartbeat rounds)
- SHOULD consider restructuring as the organization grows
- SHOULD identify suitable assignees based on existing members' `speciality` when new work arises

### Example Behavior Patterns

```
[On Heartbeat]
1. Check subordinate reports and messages
2. Check for unresolved blockers
3. Give instructions and decisions as needed
4. Record overall progress in state/current_state.md

[When a decision is needed]
1. Receive escalation from subordinate: "Should we do A or B?"
2. Check company/vision.md and past decision criteria (knowledge/)
3. Make a decision and reply to the subordinate with reasoning
4. Record the decision in knowledge/ (as a precedent for later)
```

## Mid-Level Management Anima (has supervisor and subordinates)

Between supervisor and subordinates; responsible for task decomposition, delegation, and progress management.

### Responsibilities

- Breaking down supervisor instructions into tasks and delegating them to subordinates
- Tracking subordinate progress and resolving blockers
- Escalating issues beyond their authority to the supervisor
- Consolidating subordinate outcomes and reporting to the supervisor
- Coordinating with peers (Anima that share the same supervisor)

### MUST (Required)

- When receiving instructions from the supervisor, MUST break them down into tasks and delegate to subordinates
- When receiving problem reports from subordinates, MUST escalate to the supervisor if you cannot resolve them yourself
- MUST report progress to the supervisor on a regular basis

### SHOULD (Recommended)

- SHOULD state purpose, expected outcomes, and deadlines when delegating tasks
- SHOULD assign work that leverages subordinates' strengths (`speciality`)
- SHOULD confirm with the supervisor when boundaries with peers are unclear

### MAY (Optional)

- MAY rebalance tasks among subordinates for workload fairness
- MAY record process improvements in knowledge/

### Example Behavior Patterns

```
[When receiving instructions from supervisor]
1. Understand the request and break it into the necessary tasks
2. Assign each task according to subordinates' speciality
3. Send instructions by message (include purpose, deliverables, and deadline)
4. Record in-flight tasks in state/current_state.md

[When receiving a problem report from a subordinate]
1. Confirm the issue and its impact
2. Decide whether you can resolve it within your authority
   - Can resolve → Give direction and reply to the subordinate
   - Cannot resolve → Summarize the situation and escalate to the supervisor
3. Record the handling in episodes/
```

## Worker Anima (has supervisor, no subordinates)

Executes tasks and delivers outcomes. Acts as the organization's "hands and feet," performing concrete work.

### Responsibilities

- Executing task instructions from the supervisor
- Creating deliverables and ensuring quality
- Reporting progress, completion, and issues
- Accumulating knowledge related to their `speciality`

### MUST (Required)

- MUST report to the supervisor when assigned tasks are completed
- MUST report problems or blockers to the supervisor promptly as they occur
- MUST ask the supervisor when unsure rather than deciding unilaterally

### SHOULD (Recommended)

- SHOULD record work logs in episodes/ (so you can reflect on them later)
- SHOULD save insights in knowledge/
- SHOULD coordinate directly with relevant peers to improve efficiency when applicable

### MAY (Optional)

- MAY propose operational improvements to the supervisor
- MAY turn repeated work into procedures and save them under procedures/

### Example Behavior Patterns

```
[When receiving a task]
1. Understand the instruction; ask the supervisor if anything is unclear
2. Search relevant knowledge/ and procedures/
3. Execute the work
4. Produce deliverables and report completion to the supervisor
5. Record a work log in episodes/

[When a problem occurs during work]
1. Organize what the problem is
2. Search your knowledge/ for a solution
3. If you cannot resolve it, report a summary and what you already tried to the supervisor
4. Wait for the supervisor's direction (or start another task)
```

## Independent Anima (supervisor = null, no subordinates)

An Anima with neither supervisor nor subordinates; operates autonomously. Suitable for a one-person organization or a specialized standalone role.

### Responsibilities

- All work within their `speciality`
- Autonomous judgment and execution
- Direct interaction with users (humans)

### Characteristics

- With no escalation path, MUST resolve decisions end-to-end on your own
- Organization structure may change if other Anima are added
- SHOULD use `company/vision.md` as the top-level criterion for decisions

## Role of the `speciality` Field

`speciality` is a free-text field that defines an Anima's area of expertise.

### Uses

1. **Input for other Anima**: A hint for "who should I ask about this?"
2. **Display in org context**: Shown next to the name, e.g. `bob (Development lead)`
3. **Basis for task routing**: Input when a supervisor delegates tasks to subordinates

### Effective Examples

| speciality | Typical work |
|------------|--------------|
| Backend development · API design | Server-side implementation, API design, database work |
| Frontend · UI/UX | Screen design, improving user experience |
| Project management · coordination | Schedule management, cross-team coordination |
| Quality assurance · test automation | Test design, bug finding, CI/CD |
| Customer support · help desk | Handling inquiries, organizing requests, feedback |
| Data analysis · reporting | Aggregation, visualization, decision support |
| Infrastructure · security | Server operations, monitoring, security measures |

### Notes

- `speciality` is a display label; it does not restrict permissions
- Tool and command permissions are resolved at runtime primarily as `permissions.json` (automatic migration applies when only `permissions.md` exists)
- An Anima runs normally without `speciality`, but other Anima have less to go on when routing work
- `speciality` is managed via `status.json` or the `animas` entry in `config.json` and kept consistent by org sync; applying changes follows your operations (e.g. `anima reload` or server restart)

## Role Templates

Specifying a professional role with `--role` when creating an Anima is supported **only via the Markdown character sheet**.

- Example command: `animaworks anima create --from-md PATH [--role ROLE]` (same for the deprecated `create-anima`)
- With `create_from_template` (`--template`) and `create_blank` (`--name` only), **neither** merging from `_shared/roles/<role>/defaults.json` **nor** overwrite-copying `permissions.json` / `specialty_prompt.md` from `templates/{locale}/roles/<role>/` occurs. The former copies `anima_templates/{name}` as-is; the latter copies `_blank` only. In both cases, if `status.json` is missing after copy, `_ensure_status_json` adds a minimal file `{"enabled": true}` (the current template tree does not bundle `status.json`) (`core/anima_factory.py`).

### Character sheet heading aliases (normalization)

Before loading, `_normalize_sheet_headings()` runs. On Japanese sheets, `SECTION_HEADING_ALIASES` maps the following alternate headings to standard headings, **after which** required-section validation runs.

| Alias | Normalized to |
|-------|---------------|
| `## 基本プロフィール` | `## 基本情報` |
| `## 性格` / `## 性格・キャラクター` | `## 人格` |

### Template directory structure

Role templates are split between `templates/_shared` and locale-specific paths:

| Path | Content | Locale |
|------|---------|--------|
| `templates/_shared/roles/{role}/defaults.json` | Default model and parameters | Shared |
| `templates/{locale}/roles/{role}/permissions.json` | Per-role tool permissions | ja / en |
| `templates/{locale}/roles/{role}/specialty_prompt.md` | Per-role behavioral guidance | ja / en |

`locale` comes from `locale` in `config.json`, defaulting to `ja`.
`_get_roles_dir()` (`core/anima_factory.py`) looks under `templates/{locale}/roles` and
**falls back to `en`, then `ja`, if that path does not exist**.

`defaults.json` lives at `templates/_shared/roles/<role>/defaults.json` and is shared across locales. Fields:

| Field | Description | Notes |
|-------|-------------|-------|
| `model` | Model for chat and task execution | All roles |
| `background_model` | Model for Heartbeat, cron, and other background work | engineer / manager only (other roles omit the key) |
| `context_threshold` | Compaction threshold | All roles |
| `max_turns` | Maximum turns | All roles |
| `max_chains` | Maximum chains | All roles |
| `conversation_history_threshold` | Conversation history compression threshold | All roles (templates use roughly 0.30–0.40) |
| `max_outbound_per_hour` | Hourly outbound cap (DM / Board) | Rate limiting |
| `max_outbound_per_day` | Daily outbound cap | Rate limiting |
| `max_recipients_per_run` | Max distinct recipients per run | Rate limiting |

Valid role names must match `VALID_ROLES` in code (`engineer`, `researcher`, `manager`, `writer`, `ops`, `general`).

### Available roles (values from `defaults.json`)

Model and execution parameters:

| Role | model | background_model | context_threshold | max_turns | max_chains | conversation_history_threshold |
|------|-------|------------------|-------------------|-----------|------------|--------------------------------|
| manager | claude-opus-4-6 | claude-sonnet-4-6 | 0.60 | 10000 | 3 | 0.30 |
| engineer | claude-opus-4-6 | claude-sonnet-4-6 | 0.80 | 10000 | 10 | 0.40 |
| researcher | claude-sonnet-4-6 | — | 0.50 | 10000 | 2 | 0.30 |
| writer | claude-sonnet-4-6 | — | 0.70 | 10000 | 5 | 0.30 |
| ops | ollama/glm-4.7 | — | 0.50 | 10000 | 2 | 0.30 |
| general | claude-sonnet-4-6 | — | 0.50 | 10000 | 2 | 0.30 |

Messaging caps (rate-related keys inside `defaults.json`):

| Role | max_outbound_per_hour | max_outbound_per_day | max_recipients_per_run |
|------|------------------------|----------------------|-------------------------|
| manager | 60 | 300 | 10 |
| engineer | 40 | 200 | 5 |
| researcher | 30 | 150 | 3 |
| writer | 30 | 150 | 3 |
| ops | 20 | 80 | 2 |
| general | 15 | 50 | 2 |

`create_from_md` without `--role` uses `general`. The ops default `ollama/glm-4.7` targets local setups. In bundled `templates/_shared/config_defaults/models.json`, `ollama/glm-4.7*` matches execution mode **A** (LiteLLM + tool loop). For vLLM and similar, edit `model` and `credential` in `status.json` (e.g. `openai/glm-4.7-flash`). engineer and manager can assign a lighter model to background work such as Heartbeat and cron via `background_model`.

### Application flow

1. **At creation** (`create_from_md`), order is:
   - `_apply_defaults_from_sheet()` … from the character sheet to `identity.md` / `injection.md` / (if a permissions section exists) `permissions.md` → migrate to `permissions.json`
   - `_apply_role_defaults()` … **overwrite-copy** the role's `permissions.json` and `specialty_prompt.md` (sheet-derived `permissions.json` is overwritten by the role template)
   - `_create_status_json()` … read all keys in the table above from `SHARED_ROLES_DIR` (`_shared/roles/<role>/defaults.json`), override with sheet "model" / "credential" when present, and write `status.json`. `execution_mode` is written only when the sheet's execution-mode field has a value (`Execution Mode` on English sheets, `実行モード` on Japanese; see `FIELD_NAMES` in `core/anima_factory.py`); if omitted, the key is left out and pattern resolution in `models.json` etc. applies (`_create_status_json` in `core/anima_factory.py`).
2. **On role change** (`animaworks anima set-role`): `_apply_role_defaults()` recopies `permissions.json` and `specialty_prompt.md`. Only `model`, `context_threshold`, `max_turns`, `max_chains`, and `conversation_history_threshold` are merged from `defaults.json` into `status.json`. **`background_model` and `max_outbound_*` are not updated by set-role** (edit `status.json` manually if needed). `--status-only` updates only the `role` field and those numeric keys and does not touch template files. `--no-restart` skips API-triggered automatic restart. The CLI success message mentions `permissions.md`, but what is actually overwritten is **`permissions.json`** (`cmd_anima_set_role` in `cli/commands/anima_mgmt.py`).

### Prompt injection

The role name is stored in `role` in `status.json`.
`specialty_prompt.md` is included in Group 2 of `build_system_prompt`, after bootstrap → company vision and immediately before permissions (`_build_group2` in `core/prompt/builder.py`).

**Inclusion conditions** (branching inside `_build_group2`): when the following flags are set from `trigger`, `memory.read_specialty_prompt()` is not called and the specialty section is not assembled.

- Starts with `inbox:` (Anima-to-Anima Inbox)
- `heartbeat`
- Starts with `cron:`
- Starts with `consolidation:`
- Starts with `task:` (TaskExec)

The specialty prompt is loaded only for paths **other than the above**, including **the default empty `trigger` for normal human chat**. Section priority is 3 (rigid); it may still be omitted depending on the overall system prompt character budget (`_allocate_sections`).
