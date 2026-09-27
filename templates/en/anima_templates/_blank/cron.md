# Cron: {name}

<!--
=== Cron Format Specification ===

■ Basic Structure
  ## Task Name
  schedule: <5-field cron expression>
  type: llm | command
  (Body or command/tool definition)

■ schedule: is required
  Write the `schedule:` line immediately after each task (## heading).
  If omitted, the task will not run.

■ 5-field cron expression
  schedule: minute hour day month weekday
  ┌───── minute (0-59)
  │ ┌───── hour (0-23)
  │ │ ┌───── day (1-31)
  │ │ │ ┌───── month (1-12)
  │ │ │ │ ┌───── weekday (0=Mon to 6=Sun)
  │ │ │ │ │
  * * * * *

■ Common schedule examples
  schedule: 0 9 * * *       # Every morning at 9:00
  schedule: */5 * * * *     # Every 5 minutes
  schedule: 0 9 * * 0-4     # Weekdays at 9:00 (Mon-Fri)
  schedule: 0 17 * * 4      # Every Friday at 17:00
  schedule: 0 2 * * *       # Every day at 2:00
  schedule: 30 12 1 * *     # On the 1st of every month at 12:30

■ What not to do
  ✗ ### cron expression      ← Only use ## for heading levels
  ✗ schedule: every morning at 9   ← Natural language is not allowed; use a 5-field cron expression
  ✗ (no schedule: line)     ← Always include it

■ type options
  1. LLM type (type: llm) - tasks requiring judgment or thinking
  2. Command type (type: command) - deterministic bash/tool execution

■ Options (command type only)
  skip_pattern: <regex>       — If stdout matches, skip LLM analysis
  trigger_heartbeat: false    — Do not trigger LLM analysis even if there is output

■ Detailed reference
  → See common_skills/cron-management.md
-->

## Daily Morning Work Plan
schedule: 0 9 * * *
type: llm
Check yesterday's progress from long-term memory and plan today's tasks.
Prioritize based on the philosophy and goals.
Write the results to state/current_state.md.

## Weekly Review
schedule: 0 17 * * 4
type: llm
Review this week's episodes/ and extract patterns to integrate into knowledge/.
(Memory consolidation = the brain's memory fixation during sleep, as in neuroscience)

<!--
## Run Backup
schedule: 0 2 * * *
type: command
command: /usr/local/bin/backup.sh

## Slack Notification
schedule: 0 9 * * 0-4
type: command
tool: slack_send
args:
  channel: "#general"
  message: "Good morning!"
-->