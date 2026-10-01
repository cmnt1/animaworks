<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/architecture/lifecycle.md -->
<!-- i18n: source-sha256=fc15ebd7f7ff4e9d39caf9e22e42c6aac67d6fbda00a162a69943b1044a4f2bd generated=2026-10-01 engine=local model=deepseek-v4-flash translator=2 -->

> Confirmed commit: b304b7dc

# Startup Triggers and Lifecycle

Anima is executed not only in response to requests from the server, but also triggered by messages and schedules. A root process remains resident to manage the scheduler and receive handling, while actual conversation and automated execution are offloaded to dedicated lanes in the task runner.

## Triggers and Lanes

| Trigger | Processing Executed |
|---|---|
| chat | Processes conversations with users per thread. |
| inbox | Processes messages arriving from other Anima instances or connected parties in a dedicated inbox lane. |
| heartbeat | Performs periodic checks based on instructions in `heartbeat.md` via the heartbeat task runner. |
| cron | Executes scheduled processing defined in `cron.md` via the cron task runner. |
| task | Background workers take on executable tasks from the TaskStore. |
| greet | Performs greetings after startup or at the start of a conversation via a dedicated chat task runner. |

Chat uses a per-thread conversation lock to prevent conflicts within the same conversation. Inbox and scheduled background work have separate control locks. TaskExec uses dedicated worker slots and AgentCore, and does not share the execution lock of heartbeat/Cron. Updates to file `state/current_state.md` use a process-safe state file lock.

## Heartbeat and cron

The default heartbeat interval is 30 minutes in the global configuration, and can be overridden per Anima via `status.json` in `heartbeat_interval_minutes`. The valid range is 1–1440 minutes. The global `activity_level` defaults to 100%, with an allowable range of 10–400%; higher values shorten the effective interval. `activity_schedule` can be used to switch activity levels by time of day. Active time windows are configured from `heartbeat.md`.

`cron.md` is a heading-level definition, where `schedule` holds a standard 5-field cron expression. `type`, a description, and optionally command/tool with arguments are set, and `core/supervisor/schedule_parser.py` parses them. During setup or hot-reload, only schedules that could not be parsed or registered are reported as `cron_health_*.md` notifications. There is no periodic monitoring of registered cron execution frequency or failures.

## Initial Startup and One Cycle

On initial startup, `core/anima/bootstrap_state.py` checks the definition status of `identity.md` and `injection.md`, and records the start, failure, or completion of bootstrap. The supervisor starts the process, confirms that the IPC endpoint and dependent services are ready, and then begins normal processing.

1. Map the trigger to a session type and lane, and acquire the required lock or worker slot.
2. Resolve `status.json` and common configuration, and prepare the prompt from memory, permissions, current status, messages, and other inputs.
3. The engine adapter matching the execution mode mediates model calls and tool execution, returning events to the root.
4. Finalize the response, conversation record, task status, and activity log, and save any notifications needed for subsequent processing.
5. Release the lock / worker slot, returning to a state where the root's scheduler and inbox dispatcher can accept the next request.

## Design Decisions

- **Cron is each Anima's internal clock.** It is not an organization-wide scheduler; just as a person has their own daily routines, each Anima has its own habits.
