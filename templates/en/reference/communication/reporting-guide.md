# Reporting and Escalation Guide

> **Required**: Before reporting or escalating, verify the mandatory items in `communication/message-quality-protocol.md`.

Reporting to your supervisor is the lifeblood of organizational operations.
Reporting at the right time and in the right format supports early problem detection and rapid decision-making.

## Tool Usage

Use the `send_message` tool for reporting. Observe the following constraints:

| Tool | Purpose | Notes |
|------|---------|-------|
| `send_message` | One-to-one reports and questions to supervisor or colleagues | Reports, progress, and decision requests use `intent="report"`; questions use `intent="question"`. Anima names, aliases, `slack:` / `chatwork:` (see below), etc. |
| `post_channel` | Team-wide announcements (Board) | Acknowledgments, thanks, and FYI use Board. One post per channel per run; reposts require cooldown (`heartbeat.channel_post_cooldown_s`, default 300 seconds) |
| `call_human` | Urgent notification to humans | Service outage, security incidents, etc. |

**send_message constraints**:
- `intent` is **required**; values must be **`report` or `question` only** (use `report` for reports and progress, `question` for questions). **`delegation` is not allowed** with `send_message` (the tool rejects it). For task delegation, use `delegate_task`
- Number of distinct recipients per run is limited by **`max_recipients_per_run`** (overridable in `status.json`; if unset, role defaults apply—e.g. `general` is 2). At most one message per recipient. For three or more recipients, use Board
- Use Board (`post_channel`) for additional follow-up
- **Recipients**: see “Recipient resolution” below (Anima name, human alias, direct `slack:` / `chatwork:`, etc.)
- **Note**: During a chat session with a human, `send_message` cannot target the human; reply with plain text directly

### Recipient resolution and external delivery (`core/outbound.py`)

The `to` field of `send_message` is resolved to an internal inbox or external delivery (Slack / Chatwork) in the following **priority order**. An empty string cannot be resolved and results in an error.

1. **Exact match** with a known Anima name (case-sensitive) → internal inbox. Known names are directory names directly under `~/.animaworks/animas/`
2. **Match** with a key in `external_messaging.user_aliases` in `config.json` (aliases are **case-insensitive**) → external delivery. When `external_messaging.preferred_channel` (`slack` / `chatwork`) is `slack`, use Slack if `slack_user_id` is set, otherwise Chatwork if `chatwork_room_id` is set. When `preferred_channel` is `chatwork`, prefer `chatwork_room_id`, otherwise Slack if `slack_user_id` is set. An alias with **neither ID** is an error (configure contact details in `external_messaging.user_aliases`)
3. **`slack:USERID`** (starts with `slack:`, remainder is a Slack user ID) → Slack DM directly (USERID is **normalized to uppercase** in the implementation)
4. **`chatwork:ROOMID`** (starts with `chatwork:`; only leading/trailing whitespace is stripped from ROOMID) → Chatwork room directly
5. **Slack user ID alone** (`U` + **8 or more** alphanumeric characters; case is accepted at match time, e.g. `U0123456789`) → Slack DM directly
6. **Case-insensitive match** with a known Anima name → internal (normalized to the canonical name on disk)
7. If none apply → unknown-recipient error (hint wording in the tool layer may differ during chat execution vs otherwise)

**External-facing settings** (`external_messaging` in `config.json`):

| Field | Role |
|-------|------|
| `preferred_channel` | Default channel for alias targets (`slack` / `chatwork`) |
| `user_aliases` | Alias name → `{ "slack_user_id": "...", "chatwork_room_id": "..." }` (**at least one** required) |

**External send behavior** (`send_external`):

- Try the **resolved channel first**; on failure, try **the other channel** (a second attempt exists only when both Slack and Chatwork destination IDs are present, e.g. for aliases. Direct `slack:` / `chatwork:` targets usually use that channel only)
- If delivery cannot proceed (e.g. external channel not configured), the tool result may return JSON such as `NoChannelConfigured` or `DeliveryFailed`
- Body text is converted from **Markdown to Slack mrkdwn / Chatwork**-appropriate format
- **Slack**: If `SLACK_BOT_TOKEN__{anima_name}` (Vault or shared credentials) exists for the Anima, send with the bot token and apply display name (Anima name) and **icon URL** (from Anima assets). **If there is no bot token**, prepend `[SenderAnimaName] ` to the body before sending
- **Chatwork**: Uses the write token (resolved via environment variables such as `CHATWORK_API_TOKEN_WRITE`, etc.). Via `send_message`, the body is prefixed with `[AnimaName] `

**Send limits (implementation-based)**:

- **Global (time window)**: `send_message` to internal Animas (via `Messenger.send`) and **`post_channel` share the same send counters**. Judged from `activity_log` sliding windows for the last hour and 24 hours using `dm_sent` / `message_sent` / `channel_post`. Limits use **`max_outbound_per_hour` / `max_outbound_per_day`** in `status.json` if set; otherwise **role defaults** (e.g. `general`: 15/hour, 50/day; `manager`: 60/hour, 300/day). When exceeded, sends are blocked; follow tool guidance to stash content in `current_state.md` etc. and send in a later session
- **Same pair (internal Anima DM only)**: Within `heartbeat.depth_window_s` (default 600 seconds = 10 minutes), up to `heartbeat.max_depth` (default 6 turns). When exceeded, sends to that peer are blocked (wait until the next window)

## When to Report

### Immediate Reports (MUST)

As soon as you recognize any of the following, report to your supervisor immediately:

| Situation | Reason | Example |
|-----------|--------|---------|
| Task completed | Supervisor needs to decide next actions | Deploy done, report finished |
| Error or outage | Enable early response | API down, data inconsistency detected |
| Decision needed | Escalate decisions outside your authority | Policy change proposal, request for more resources |
| Deadline slip is certain | Supervisor needs to adjust schedule | Blocker, work stopped |
| Security concern | Immediate action required | Signs of unauthorized access, suspected credential leak |

### Routine Reports (SHOULD)

| Situation | Frequency | Content |
|-----------|-----------|---------|
| Daily summary | Daily (end of business day) | Today’s results, tomorrow’s plan |
| Weekly reflection | Weekly (Friday) | Week’s results, issues, next week’s plan |
| Long-running task progress | As appropriate (guide: every 2–3 days) | Progress %, remaining work, blockers |

### When Not to Report

- Memory writes and housekeeping (internal work)
- Routine work with no anomalies (equivalent to `HEARTBEAT_OK` on heartbeat)
- Tasks where the supervisor explicitly said reporting is not needed

## Report Format

### SCANA Format

Structure reports with these five elements. You do not need every item; pick based on context.

| Item | English | Description | MUST/MAY |
|------|---------|-------------|----------|
| Situation | Situation | What is happening now | MUST |
| Cause | Cause | Why (if known) | MAY |
| Action taken | Action taken | What you did | SHOULD |
| Next steps | Next steps | What you will do / what you need decided | MUST |
| Appendix | Appendix | Related logs, file paths, numbers | MAY |

### Thread Continuation When Replying

When replying to a message from your supervisor, set `reply_to` (message ID being replied to) and `thread_id` (thread ID) to preserve context. ID format is `YYYYMMDD_HHMMSS_ffffff` (e.g. `20260215_093000_123456`).

```
send_message(
    to="manager",
    content="Understood. I will address this by 3pm.",
    intent="report",
    reply_to="20260215_093000_123456",
    thread_id="20260215_090000_000000"
)
```

### Format Example

```
send_message(
    to="manager",
    content="""[Completed] Monthly sales data aggregation

Situation: January 2026 sales data aggregation is complete.
Action taken: Aggregated by department and category; computed month-over-month comparison.
Next steps: No action required on your side. Please review the report.
Appendix: /shared/reports/sales_summary_202601.md""",
    intent="report"
)
```

## Report Templates by Type

### Completion Report

When a task has completed successfully.

```
send_message(
    to="manager",
    content="""[Completed] {task_name}

Situation: {task_name} is complete.
Deliverable: {file path or result summary}
Duration: {time spent}
Notes: {if any}""",
    intent="report"
)
```

**Example:**

```
send_message(
    to="manager",
    content="""[Completed] API spec v2.1 update

Situation: Applied v2.1 changes to the API specification.
Deliverable: /shared/docs/api-spec.md (diff: sections 3.2, 4.1 updated)
Duration: ~45 minutes
Notes: Added three pagination examples.""",
    intent="report"
)
```

### Error Report

When an error or outage occurs.

```
send_message(
    to="manager",
    content="""[Error] {what happened}

Situation: {description of current state}
Cause: {cause, to the extent known}
Impact: {what is stopped, who is affected}
Action taken: {what you tried and the outcome}
Next steps: {proposed follow-up / decisions needed}""",
    intent="report"
)
```

**Example:**

```
send_message(
    to="manager",
    content="""[Error] Scheduled batch job failure

Situation: The 9:00 AM data sync batch has failed three times in a row.
Cause: External API response timeout (exceeds 30s). Provider-side outage is likely.
Impact: Data since this morning is unsynced. Dashboard numbers are stuck as of yesterday.
Action taken: Extended timeout to 60s and retried — same failure. Checked provider status page — no maintenance notice.
Next steps: We need to contact the API provider. Please advise.""",
    intent="report"
)
```

### Decision Request (decision escalation)

When a decision is outside your authority.

```
send_message(
    to="manager",
    content="""[Decision needed] {what needs deciding}

Situation: {current situation}
Options:
A. {option A} — Pros: {benefits} / Cons: {drawbacks}
B. {option B} — Pros: {benefits} / Cons: {drawbacks}
My recommendation: {A or B} (reason: {why})

Please advise.""",
    intent="report"
)
```

**Example:**

```
send_message(
    to="manager",
    content="""[Decision needed] Log retention change

Situation: Disk usage is at 85% and is expected to exceed 90% within a week.
Options:
A. Shorten log retention from 90 to 30 days — Pros: ~50 GB freed immediately / Cons: investigation using old logs becomes impossible
B. Add storage (500 GB) — Pros: keep logs / Cons: higher monthly cost (~$50/month)
C. Move old logs to archive storage — Pros: retain logs and control cost / Cons: ~2 days to implement
My recommendation: C (good balance of cost and data retention)

Please advise.""",
    intent="report"
)
```

### Progress Report

Mid-task update for long-running work.

```
send_message(
    to="manager",
    content="""[Progress] {task_name}

Progress: {completed work / overall %}
Remaining: {not yet done}
Blockers: {if any; otherwise "none"}
Outlook: {whether you will meet the deadline}""",
    intent="report"
)
```

**Example:**

```
send_message(
    to="manager",
    content="""[Progress] User notification feature implementation

Progress: Phase 1 (design) complete; Phase 2 (implementation) ~70% complete
  - Email notification: done
  - Slack notification: done
  - In-app notification: in progress (~1 day left)
Remaining: In-app notification implementation + test code
Blockers: None
Outlook: Will meet the 2/20 deadline.""",
    intent="report"
)
```

## Daily Summary Format

End-of-day recap sent to your supervisor.

### Template

```
send_message(
    to="manager",
    content="""[Daily Summary] 2026-02-15

■ Completed
- {completed task 1}
- {completed task 2}

■ In progress
- {task in progress} (progress: {XX}%, outlook: {deadline})

■ Issues / concerns
- {if any}

■ Tomorrow
- {plan 1}
- {plan 2}""",
    intent="report"
)
```

### Example

```
send_message(
    to="manager",
    content="""[Daily Summary] 2026-02-15

■ Completed
- API spec v2.1 update (/shared/docs/api-spec.md)
- Fixed timezone handling bug in log monitoring script

■ In progress
- User notification feature implementation (progress: 70%, target completion 2/20)

■ Issues / concerns
- External API responses appear slower (no impact so far; continuing to monitor)

■ Tomorrow
- Finish in-app notification implementation
- Start writing test code""",
    intent="report"
)
```

## Urgent vs Routine Reports

### Urgent Report (immediate, MUST)

If any of the following apply, report immediately even if it means interrupting other work:

- **Service outage**: User-visible failure or degradation
- **Data loss or corruption**: Risk of unrecoverable state
- **Security incident**: Unauthorized access, suspected information leak
- **Deadline miss confirmed**: A committed deadline will definitely not be met

MUST: Prefix urgent messages with `[URGENT]` at the beginning.
For service outage, data loss, or security incidents that need immediate human action, also use `call_human`.

```
send_message(
    to="manager",
    content="""[URGENT] Production database latency

Situation: Production DB response time is ~10× normal (avg 300ms → 3000ms).
Impact: Web UI page loads take 10+ seconds.
In progress: Started identifying slow queries. Will follow up within 10 minutes.""",
    intent="report"
)
```

### Routine Report (next heartbeat or daily summary)

Lower urgency; may be batched:

- Mid-task progress when the plan is on track
- Minor issues you have already resolved yourself
- Improvement ideas and proposals

## Escalation Decision Flowchart

Steps to decide whether and how to escalate:

```
1. Can you resolve this within your authority?
   → Yes: Handle it, then report the outcome
   → No: Go to step 2

2. Is it urgent? (service impact, data loss risk)
   → Yes: Escalate immediately as [URGENT]
   → No: Go to step 3

3. Can you lay out decision options?
   → Yes: Report as [Decision needed] with options and a recommendation
   → No: Report the situation as-is and ask for direction
```

## Report Guidelines

### Do (MUST/SHOULD)

- MUST: In `send_message`, set `intent` to **`"report"`** (reports and progress) or **`"question"`** (questions). **`"delegation"`** is invalid (use `delegate_task` for delegation)
- MUST: Separate fact from speculation. Label speculation with phrases like “likely” or “probably”
- MUST: State impact clearly—**what** is affected and **who** is affected
- SHOULD: Include what you tried and the outcome so your supervisor does not repeat the same steps
- SHOULD: Propose next actions yourself; do not only wait for instructions

### Avoid

- Long narrative before the conclusion (lead with the conclusion)
- Reports that only say “something went wrong” with no concrete detail
- Packing several unrelated topics into one message (split by topic)
- Hiding problems or downplaying severity (communicate the situation accurately)
- More than one `send_message` to the same recipient in the same run (one message only; use Board for extra contact). You also cannot DM more people than `max_recipients_per_run` allows in one run
