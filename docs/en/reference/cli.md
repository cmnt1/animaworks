<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/reference/cli.md -->
<!-- i18n: source-sha256=92b56543103c512cc42f576f51d3e9dc48a56d9fd976fa97bbe6d048019e75ba generated=2026-09-28 engine=luna model=gpt-6-luna translator=2 -->

# CLI Reference: `animaworks`

Generated from the argparse definition of the `animaworks` command.

## Global Options

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --gateway-url | option | — | — | Gateway URL |
| --data-dir | option | — | — | Override runtime data directory (default: ~/.animaworks or ANIMAWORKS_DATA_DIR) |

## `anima`

Manage anima processes

`usage: animaworks anima [-h]
                        {restart,status,create,delete,disable,enable,list,info,repair-bootstrap,permissions,set-model,codex-yolo,set-background-model,set-outbound-limit,reload,set-role,rename,audit}
                        ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `anima audit`

Audit a subordinate anima's recent activity

`usage: animaworks anima audit [-h] [--all] [--days DAYS] [--since SINCE]
                              [--date DATE]
                              [anima]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Target anima name (omit with --all for all) |
| --all | flag | false | — | Audit all animas |
| --days | option | 1 | — | Number of days to audit (default: 1, max: 30) |
| --since | option | — | — | Start time in HH:MM format (today, JST). Overrides --days when specified |
| --date | option | — | — | Specific date (YYYY-MM-DD, 'today', or 'yesterday'). Shows only that day's activity |

## `anima codex-yolo`

Set Codex-mode Animas to YOLO sandbox defaults

`usage: animaworks anima codex-yolo [-h] [--all] [--restart] [anima]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name (not required with --all) |
| --all | flag | false | — | Apply to all enabled Codex-mode animas |
| --restart | flag | false | — | Restart updated animas when the server is running |

## `anima create`

Create a new anima

`usage: animaworks anima create [-h] [--name NAME] [--template TEMPLATE]
                               [--from-md PATH] [--supervisor SUPERVISOR]
                               [--role {engineer,researcher,manager,writer,ops,general}]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --name | option | — | — | Anima name (required for blank, optional for template/md) |
| --template | option | — | — | Create from a named template |
| --from-md | option | — | — | Create from an MD file |
| --supervisor | option | — | — | Supervisor anima name (overrides character sheet) |
| --role | option | — | engineer, researcher, manager, writer, ops, general | Role template to apply (default: general) |

## `anima delete`

Delete an anima (with optional archive)

`usage: animaworks anima delete [-h] [--no-archive] [--force] anima`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name to delete |
| --no-archive | flag | false | — | Skip creating a ZIP archive before deletion |
| --force | flag | false | — | Skip confirmation prompt |

## `anima disable`

Disable (休養) an anima

`usage: animaworks anima disable [-h] anima`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name to disable |

## `anima enable`

Enable (復帰) an anima

`usage: animaworks anima enable [-h] anima`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name to enable |

## `anima info`

Show detailed configuration for an anima

`usage: animaworks anima info [-h] [--json] anima`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name |
| --json | flag | false | — | Output as JSON |

## `anima list`

List all animas with status

`usage: animaworks anima list [-h] [--local]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --local | flag | false | — | Scan filesystem directly |

## `anima permissions`

Display an Anima's permission configuration

`usage: animaworks anima permissions [-h] anima`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name |

## `anima reload`

Hot-reload anima config from status.json

`usage: animaworks anima reload [-h] [--all] [anima]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name (not required with --all) |
| --all | flag | false | — | Reload config for all running animas |

## `anima rename`

Rename an anima

`usage: animaworks anima rename [-h] [--force] old_name new_name`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| old_name | positional | — | — | Current anima name |
| new_name | positional | — | — | New anima name |
| --force | flag | false | — | Skip confirmation prompt |

## `anima repair-bootstrap`

Inspect or repair first-run bootstrap state

`usage: animaworks anima repair-bootstrap [-h]
                                         (--status | --retry | --complete | --fresh)
                                         anima`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name |
| --status | flag | false | — | Show bootstrap state and validation errors without changing files |
| --retry | flag | false | — | Restore bootstrap artifacts and prepare another bootstrap attempt |
| --complete | flag | false | — | Archive stale bootstrap artifacts and mark a fully defined Anima as completed |
| --fresh | flag | false | — | Archive runtime data and recreate a blank Anima while preserving model settings |

## `anima restart`

Restart an anima process

`usage: animaworks anima restart [-h] anima`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name |

## `anima set-background-model`

Set heartbeat/cron model

`usage: animaworks anima set-background-model [-h] [--credential CREDENTIAL]
                                             [--all] [--clear]
                                             [anima] [model]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name |
| model | positional | — | — | Background model name |
| --credential | option | — | — | Credential name |
| --all | flag | false | — | Apply to all enabled animas |
| --clear | flag | false | — | Remove background model override |

## `anima set-model`

Change the main model of the specified anima.

`usage: animaworks anima set-model [-h] [--credential CREDENTIAL] [--all]
                                  [anima] [model]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name (not required with --all) |
| model | positional | — | — | Model name (e.g. azure/gpt-4.1-mini) |
| --credential | option | — | — | Credential name |
| --all | flag | false | — | Apply to all enabled animas |

## `anima set-outbound-limit`

Set per-Anima outbound message limits

`usage: animaworks anima set-outbound-limit [-h] [--per-hour PER_HOUR]
                                           [--per-day PER_DAY]
                                           [--per-run PER_RUN] [--clear]
                                           name`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| name | positional | — | — | Anima name |
| --per-hour | option | — | — | Max outbound messages per hour |
| --per-day | option | — | — | Max outbound messages per day |
| --per-run | option | — | — | Max DM recipients per run |
| --clear | flag | false | — | Clear overrides (fallback to role defaults) |

## `anima set-role`

Change an anima's role

`usage: animaworks anima set-role [-h] [--status-only] [--no-restart]
                                 anima
                                 {engineer,researcher,manager,writer,ops,general}`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name |
| role | positional | — | engineer, researcher, manager, writer, ops, general | New role to assign |
| --status-only | flag | false | — | Update status.json role field only; skip template file re-application |
| --no-restart | flag | false | — | Skip automatic restart after role change |

## `anima status`

Show anima process status

`usage: animaworks anima status [-h] [anima]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name (omit for all animas) |

## `board`

Board shared channel operations

`usage: animaworks board [-h] {read,post,dm-history} ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `board dm-history`

Read DM history with peer

`usage: animaworks board dm-history [-h] [--limit LIMIT] from_anima peer`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| from_anima | positional | — | — | Self anima name |
| peer | positional | — | — | Peer anima name |
| --limit | option | 20 | — | Max messages |

## `board post`

Post to channel

`usage: animaworks board post [-h] from_anima channel text`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| from_anima | positional | — | — | Sender anima name |
| channel | positional | — | — | Channel name |
| text | positional | — | — | Message text |

## `board read`

Read channel messages

`usage: animaworks board read [-h] [--limit LIMIT] [--human-only] channel`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| channel | positional | — | — | Channel name (e.g. general, ops) |
| --limit | option | 20 | — | Max messages |
| --human-only | flag | false | — | Show human messages only |

## `chat`

Chat with an anima

`usage: animaworks chat [-h] [--local] [--from FROM_PERSON]
                       [--thread THREAD_ID] [--no-tui] [--resume [SESSION_ID]]
                       [--sessions] [--user USER] [--password PASSWORD]
                       [--no-reattach]
                       [anima] [message]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name |
| message | positional | — | — | Message to send (omit to open the interactive TUI) |
| --local | flag | false | — | (deprecated) Direct mode (no gateway) |
| --from, --as | option | "human" | — | Sender name (default: human) |
| --thread | option | "default" | — | Thread ID (default: default) |
| --no-tui | flag | false | — | Do not open the TUI when no message is given; read stdin instead |
| --resume | option | — | — | Resume a previous TUI session (optional SESSION_ID; default latest) |
| --sessions | flag | false | — | List saved TUI sessions and exit |
| --user | option | — | — | Username for authenticated gateways |
| --password | option | — | — | Password for authenticated gateways (visible in process list) |
| --no-reattach | flag | false | — | Do not re-attach to an in-flight stream on startup |

## `company`

Manage company workspaces, anima memberships, and company-owned assets.

`usage: animaworks company [-h] {create,list,assign,adopt,split,export} ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `company adopt`

Move data-directory assets under a company, first backing them up and normally leaving relative symbolic links at their old paths.

`usage: animaworks company adopt [-h] --to NAME [--dest SUBDIR] [--no-symlink]
                                path [path ...]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| path | positional | — | — | Data-directory-relative or absolute asset path(s) |
| --to | option | — | — | Destination company |
| --dest | option | — | shared, knowledge, skills, credentials, . | Destination subdirectory (default: infer from each source) |
| --no-symlink | flag | false | — | Do not leave a symbolic link at the old path |

## `company assign`

Assign one or more animas to a company, or remove their company assignment.

`usage: animaworks company assign [-h] (--to NAME | --unassign)
                                 anima [anima ...]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name(s) |
| --to | option | — | — | Destination company |
| --unassign | flag | false | — | Remove the company assignment |

## `company create`

Create a company workspace, or add any missing scaffold to an existing one.

`usage: animaworks company create [-h] [--display-name DISPLAY_NAME] name`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| name | positional | — | — | Company name ([a-z0-9][a-z0-9_-]*) |
| --display-name | option | — | — | Human-readable company name (default: company name) |

## `company export`

Collect a company's members and assets into a portable migration bundle, with secrets redacted and remaining migration work documented.

`usage: animaworks company export [-h] --out DIR name`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| name | positional | — | — | Company name |
| --out | option | — | — | Output directory (must not already contain files) |

## `company list`

List all companies, their display names and member counts, plus unassigned animas.

`usage: animaworks company list [-h]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `company split`

Plan or execute company creation, anima assignment, and asset adoption from a manifest.

`usage: animaworks company split [-h] --manifest FILE [--execute]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --manifest | option | — | — | YAML or JSON split manifest |
| --execute | flag | false | — | Execute the plan (default: dry-run only) |

## `config`

Manage configuration

`usage: animaworks config [-h] [--interactive] {get,set,list} ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --interactive, -i | flag | false | — | Interactive setup wizard |

## `config get`

Get a config value

`usage: animaworks config get [-h] [--show-secrets] key`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| key | positional | — | — | Dot-notation key (e.g. system.timezone) |
| --show-secrets | flag | false | — | Show API key values |

## `config list`

List all config values

`usage: animaworks config list [-h] [--section SECTION] [--show-secrets]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --section | option | — | — | Filter by section |
| --show-secrets | flag | false | — | Show API key values |

## `config set`

Set a config value

`usage: animaworks config set [-h] key value`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| key | positional | — | — | Dot-notation key |
| value | positional | — | — | Value to set |

## `cost`

cli.cost_help

`usage: animaworks cost [-h] [--days DAYS] [--today] [--json] [anima]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name (omit for all animas) |
| --days | option | 30 | — | Number of days to aggregate (default: 30) |
| --today | flag | false | — | Show today only |
| --json | flag | false | — | Output as JSON |

## `cron-guard`

Inspect and re-enable auto-disabled cron tasks

`usage: animaworks cron-guard [-h] {list,enable} ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `cron-guard enable`

Re-enable an auto-disabled cron task

`usage: animaworks cron-guard enable [-h] anima task`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name |
| task | positional | — | — | Cron task name |

## `cron-guard list`

List auto-disabled cron tasks

`usage: animaworks cron-guard list [-h] anima`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name |

## `demo`

Run the 3-agent demo team (no API key needed if Claude Code or Codex is logged in)

`usage: animaworks demo [-h]
                       [--preset {en-anime,en-business,ja-anime,ja-business}]
                       [--data-dir DATA_DIR] [--port PORT] [--host HOST]
                       [--reset]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --preset | option | "en-business" | en-anime, en-business, ja-anime, ja-business | — |
| --data-dir | option | "~/.animaworks-demo" | — | — |
| --port | option | 18501 | — | — |
| --host | option | "0.0.0.0" | — | — |
| --reset | flag | false | — | — |

## `heartbeat`

Trigger heartbeat

`usage: animaworks heartbeat [-h] [--local] anima`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name |
| --local | flag | false | — | (deprecated) Direct mode (no gateway) |

## `import`

Import Hermes or OpenClaw data into AnimaWorks

`usage: animaworks import [-h] {hermes,openclaw} ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `import hermes`

Import Hermes Agent data

`usage: animaworks import hermes [-h] --path PATH [--dry-run | --apply]
                                [--replace] [--json] [--common-skills]
                                [--target-anima TARGET_ANIMA]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --path | option | — | — | Source directory, e.g. ~/.hermes or ~/.openclaw |
| --dry-run | flag | false | — | Preview without changing the runtime filesystem |
| --apply | flag | false | — | Apply importable items and write migration report |
| --replace | flag | false | — | Replace existing generated targets after backup manifest |
| --json | flag | false | — | Output JSON instead of Markdown |
| --common-skills | flag | false | — | Import skills into common_skills/community |
| --target-anima | option | — | — | Target anima for personal skills, usage, tasks, and drafts |

## `import openclaw`

Import OpenClaw data

`usage: animaworks import openclaw [-h] --path PATH [--dry-run | --apply]
                                  [--replace] [--json] --target-anima
                                  TARGET_ANIMA`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --path | option | — | — | Source directory, e.g. ~/.hermes or ~/.openclaw |
| --dry-run | flag | false | — | Preview without changing the runtime filesystem |
| --apply | flag | false | — | Apply importable items and write migration report |
| --replace | flag | false | — | Replace existing generated targets after backup manifest |
| --json | flag | false | — | Output JSON instead of Markdown |
| --target-anima | option | — | — | Target anima for generated drafts |

## `index`

Index memory files into vector database for hybrid search.

`usage: animaworks index [-h] [--anima ANIMA] [--full] [--shared] [--dry-run]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --anima | option | — | — | Index only this anima's memories (default: all animas) |
| --full | flag | false | — | Force full re-indexing (delete existing index and rebuild) |
| --shared | flag | false | — | Index shared collections (common_knowledge + common_skills) into each enabled anima's DB |
| --dry-run | flag | false | — | Show what would be indexed without actually indexing |

## `init`

Initialize the runtime directory and create animas as needed.

`usage: animaworks init [-h]
                       [--force | --template NAME | --from-md PATH | --blank NAME | --skip-anima]
                       [--name NAME]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --force | flag | false | — | Merge missing template files into existing runtime |
| --template | option | — | — | Non-interactive: create anima from named template |
| --from-md | option | — | — | Non-interactive: create anima from MD file |
| --blank | option | — | — | Non-interactive: create blank anima with given name |
| --skip-anima | flag | false | — | Initialize infrastructure only, skip anima creation |
| --name | option | — | — | Override anima name (used with --from-md) |

## `internal`

Internal tools for Anima use

`usage: animaworks internal [-h]
                           {archive-memory,check-permissions,create-skill,manage-channel,list-background-tasks,check-background-task}
                           ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `internal archive-memory`

Archive a memory file

`usage: animaworks internal archive-memory [-h] path`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| path | positional | — | — | Relative path (e.g. knowledge/old-notes.md) |

## `internal check-background-task`

Check a specific task

`usage: animaworks internal check-background-task [-h] task_id`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| task_id | positional | — | — | Task ID |

## `internal check-permissions`

Check tool permission

`usage: animaworks internal check-permissions [-h] tool_name [action]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| tool_name | positional | — | — | Tool name |
| action | positional | "" | — | Optional action |

## `internal create-skill`

Create a skill file

`usage: animaworks internal create-skill [-h] [--content CONTENT] name`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| name | positional | — | — | Skill name (or name.md) |
| --content | option | — | — | Content (default: stdin) |

## `internal list-background-tasks`

List background tasks

`usage: animaworks internal list-background-tasks [-h]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `internal manage-channel`

Create or archive a channel

`usage: animaworks internal manage-channel [-h] {create,archive} channel`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| action | positional | — | create, archive | Action |
| channel | positional | — | — | Channel name |

## `logs`

View anima logs

`usage: animaworks logs [-h] [--all] [--lines LINES] [--date DATE] [anima]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Anima name (required unless --all) |
| --all | flag | false | — | Show all logs (server + all animas) |
| --lines | option | 50 | — | Number of lines to show (default: 50) |
| --date | option | — | — | Specific date (YYYYMMDD format) |

## `mcp`

Run a stdio MCP server for an anima

`usage: animaworks mcp [-h] --anima ANIMA [--project PROJECT] [--tools TOOLS]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --anima | option | — | — | Anima name |
| --project | option | — | — | Default project archive |
| --tools | option | "search_memory,read_memory_file,write_memory_file" | — | Comma-separated exposed tools |

## `migrate`

Run required migrations on runtime data.

`usage: animaworks migrate [-h] [--dry-run] [--verbose] [--list] [--force]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --dry-run | flag | false | — | Preview changes without modifying anything |
| --verbose | flag | false | — | Show detailed file-level changes |
| --list | flag | false | — | List all migration steps and their status |
| --force | flag | false | — | Re-apply all migrations regardless of state |

## `models`

Model information and catalog

`usage: animaworks models [-h] {list,info,show} ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `models info`

Show resolved mode and context for a model

`usage: animaworks models info [-h] model`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| model | positional | — | — | Model name (e.g. claude-sonnet-4-6) |

## `models list`

List known models

`usage: animaworks models list [-h] [--mode {A,C,D,G,S,X,a,c,d,g,s,x}] [--json]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --mode | option | — | A, C, D, G, S, X, a, c, d, g, s, x | Filter by execution mode |
| --json | flag | false | — | Output as JSON |

## `models show`

Show current models.json contents

`usage: animaworks models show [-h] [--json]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --json | flag | false | — | Output raw JSON |

## `optimize-assets`

Optimize existing 3D assets (strip meshes, compress, simplify)

`usage: animaworks optimize-assets [-h] [--anima ANIMA] [--dry-run]
                                  [--simplify [RATIO]] [--texture-compress]
                                  [--texture-resize RES] [--all]
                                  [--skip-backup]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --anima, -a | option | — | — | Optimize assets for a specific anima only |
| --dry-run | flag | false | — | Show what would be done without making changes |
| --simplify | option | — | — | Simplify meshes (default ratio: 0.27 ≈ 30K→8K polygons) |
| --texture-compress | flag | false | — | Convert textures to WebP format |
| --texture-resize | option | — | — | Resize textures to RES×RES (default: 1024 when --texture-compress is set) |
| --all | flag | false | — | Apply all optimizations: strip + simplify + texture + draco |
| --skip-backup | flag | false | — | Skip creating backup of original assets |

## `profile`

Manage multiple AnimaWorks instances (multi-tenant)

`usage: animaworks profile [-h]
                          {list,add,remove,start,stop,start-all,stop-all} ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `profile add`

Register a new profile

`usage: animaworks profile add [-h] [--data-dir DATA_DIR] [--port PORT] name`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| name | positional | — | — | Profile name |
| --data-dir | option | — | — | Data directory (default: ~/.animaworks/<name>) |
| --port | option | — | — | Port (default: auto-assign from 18500, step 10) |

## `profile list`

List all profiles with status

`usage: animaworks profile list [-h]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `profile remove`

Remove profile registration

`usage: animaworks profile remove [-h] name`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| name | positional | — | — | Profile name |

## `profile start`

Start server for profile

`usage: animaworks profile start [-h] [--host HOST] name`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| name | positional | — | — | Profile name |
| --host | option | — | — | Host (default: 0.0.0.0) |

## `profile start-all`

Start all profiles

`usage: animaworks profile start-all [-h] [--host HOST]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --host | option | — | — | Host (default: 0.0.0.0) |

## `profile stop`

Stop server for profile

`usage: animaworks profile stop [-h] [--force] name`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| name | positional | — | — | Profile name |
| --force | flag | false | — | Force stop (SIGKILL after timeout) |

## `profile stop-all`

Stop all running profiles

`usage: animaworks profile stop-all [-h] [--force]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --force | flag | false | — | Force stop (SIGKILL after timeout) |

## `rag-repair-status`

Show RAG repair state for all animas

`usage: animaworks rag-repair-status [-h] [--json]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --json | flag | false | — | Print structured JSON |

## `remake-assets`

Regenerate character assets using Vibe Transfer to match the art style of a reference anima. Supports selective step execution and automatic backup.

`usage: animaworks remake-assets [-h] --style-from STYLE_FROM [--steps STEPS]
                                [--prompt PROMPT]
                                [--vibe-strength VIBE_STRENGTH]
                                [--vibe-info-extracted VIBE_INFO_EXTRACTED]
                                [--seed SEED]
                                [--image-style {anime,realistic}]
                                [--no-backup] [--dry-run]
                                anima`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| anima | positional | — | — | Name of the anima whose assets to remake |
| --style-from | option | — | — | Anima name to use as style reference (their fullbody image) |
| --steps | option | — | — | Comma-separated list of steps to run (choices: fullbody, bustup, icon, chibi, 3d, rigging, animations). Default: all steps |
| --prompt | option | — | — | Override character prompt (default: read from prompt.txt) |
| --vibe-strength | option | 0.6 | — | Vibe Transfer strength 0.0-1.0 (default: 0.6) |
| --vibe-info-extracted | option | 0.8 | — | Vibe Transfer information extraction 0.0-1.0 (default: 0.8) |
| --seed | option | — | — | Seed for reproducibility (fullbody generation only) |
| --image-style | option | — | anime, realistic | Image style (default: from config.json image_gen.image_style) |
| --no-backup | flag | false | — | Skip automatic backup of existing assets |
| --dry-run | flag | false | — | Show what would be done without making API calls |

## `repair-rag`

Rebuild RAG through the active phase3 vector owner.

`usage: animaworks repair-rag [-h]
                             [--anima ANIMA | --all | --suspect-only | --list-suspects]
                             [--full] [--shared]
                             [--window-minutes WINDOW_MINUTES]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --anima | option | — | — | Anima name to repair |
| --all | flag | false | — | Repair all enabled animas |
| --suspect-only | flag | false | — | Repair animas with recent RAG corruption evidence |
| --list-suspects | flag | false | — | List suspected corrupt RAG DBs without repairing |
| --full | flag | false | — | Required confirmation for destructive quarantine and full rebuild |
| --shared | flag | false | — | Accepted for compatibility; phase3 always rebuilds shared collections too |
| --window-minutes | option | — | — | Lookback window for --suspect-only/--list-suspects (default: repair config window) |
| --reason | option | "manual_repair_rag_cli" | — | ==SUPPRESS== |

## `reset`

Stop server, delete runtime directory, and re-initialize

`usage: animaworks reset [-h] [--restart]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --restart | flag | false | — | Start the server after reset |

## `restart`

Restart the server (stop then start)

`usage: animaworks restart [-h] [--host HOST] [--port PORT] [--foreground]
                          [--force]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --host | option | "0.0.0.0" | — | — |
| --port | option | 18500 | — | — |
| --foreground, -f | flag | false | — | Run in foreground with log output (default: daemonize) |
| --force | flag | false | — | Force stop: SIGKILL after SIGTERM timeout, also kill orphan runners |

## `send`

Send message to an anima (sender may be an anima or a human user)

`usage: animaworks send [-h] [--thread-id THREAD_ID] [--reply-to REPLY_TO]
                       [--intent INTENT]
                       from_person to_person message`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| from_person | positional | — | — | Sender name (non-anima names are sent as human) |
| to_person | positional | — | — | Recipient name |
| message | positional | — | — | Message content |
| --thread-id | option | — | — | Thread ID |
| --reply-to | option | — | — | Reply to message ID |
| --intent | option | "" | — | Message intent: delegation, report, question, or empty |

## `serve`

Start the server (alias for start)

`usage: animaworks serve [-h] [--host HOST] [--port PORT] [--foreground]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --host | option | "0.0.0.0" | — | — |
| --port | option | 18500 | — | — |
| --foreground, -f | flag | false | — | Run in foreground with log output (default: daemonize) |

## `skills`

Install and manage Skill Hub imports

`usage: animaworks skills [-h]
                         {install,list,inspect,remove,ledger,rollback,quarantine}
                         ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `skills inspect`

Inspect an installed or quarantined skill

`usage: animaworks skills inspect [-h] [--target {personal,common}]
                                 [--anima ANIMA]
                                 skill_name`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| skill_name | positional | — | — | Skill name |
| --target | option | "personal" | personal, common | Install target |
| --anima | option | — | — | Anima name for personal target |

## `skills install`

Install a skill from a local path, URL, or GitHub source

`usage: animaworks skills install [-h] [--target {personal,common}]
                                 [--anima ANIMA] [--dry-run] [--replace]
                                 [--force] [--quarantine]
                                 [--trust-level {community,untrusted}]
                                 source`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| source | positional | — | — | Local path, direct URL, or github:owner/repo/path |
| --target | option | "personal" | personal, common | Install target |
| --anima | option | — | — | Anima name for personal target |
| --dry-run | flag | false | — | Stage and scan without installing |
| --replace | flag | false | — | Replace an existing skill after creating a backup |
| --force | flag | false | — | Accepted for compatibility; import policy still applies |
| --quarantine | flag | false | — | Install into quarantine instead of active catalog |
| --trust-level | option | "community" | community, untrusted | Trust level to apply to active installs |

## `skills ledger`

List skill content changes

`usage: animaworks skills ledger [-h] [--anima ANIMA] [skill_name]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| skill_name | positional | — | — | Filter by skill name |
| --anima | option | — | — | Filter personal history to one Anima |

## `skills list`

List installed skills

`usage: animaworks skills list [-h] [--target {personal,common}]
                              [--anima ANIMA] [--quarantine]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --target | option | "personal" | personal, common | Install target |
| --anima | option | — | — | Anima name for personal target |
| --quarantine | flag | false | — | List quarantine entries |

## `skills quarantine`

Manage quarantined skills

`usage: animaworks skills quarantine [-h] {list,promote} ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `skills quarantine list`

List quarantined skills

`usage: animaworks skills quarantine list [-h] [--target {personal,common}]
                                         [--anima ANIMA]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --target | option | "personal" | personal, common | Install target |
| --anima | option | — | — | Anima name for personal target |

## `skills quarantine promote`

Promote a quarantined skill after approval

`usage: animaworks skills quarantine promote [-h] --approval-id APPROVAL_ID
                                            [--replace]
                                            [--trust-level {community,untrusted}]
                                            [--target {personal,common}]
                                            [--anima ANIMA]
                                            skill_name`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| skill_name | positional | — | — | Skill name |
| --approval-id | option | — | — | Human approval identifier |
| --replace | flag | false | — | Replace existing active skill with backup |
| --trust-level | option | "community" | community, untrusted | Trust level to apply after promotion |
| --target | option | "personal" | personal, common | Install target |
| --anima | option | — | — | Anima name for personal target |

## `skills remove`

Remove an installed or quarantined skill

`usage: animaworks skills remove [-h] [--target {personal,common}]
                                [--anima ANIMA]
                                skill_name`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| skill_name | positional | — | — | Skill name |
| --target | option | "personal" | personal, common | Install target |
| --anima | option | — | — | Anima name for personal target |

## `skills rollback`

Rollback one skill content change by ledger ID

`usage: animaworks skills rollback [-h] --anima ANIMA id`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| id | positional | — | — | Ledger entry ID |
| --anima | option | — | — | Anima context/owner for the rollback |

## `start`

Start the AnimaWorks server

`usage: animaworks start [-h] [--host HOST] [--port PORT] [--foreground]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --host | option | "0.0.0.0" | — | — |
| --port | option | 18500 | — | — |
| --foreground, -f | flag | false | — | Run in foreground with log output (default: daemonize) |

## `status`

Show system status from gateway

`usage: animaworks status [-h]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `stop`

Stop the running server

`usage: animaworks stop [-h] [--force]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --force | flag | false | — | Force stop: SIGKILL after SIGTERM timeout, also kill orphan runners |

## `supervisor`

Supervisor tools for animas

`usage: animaworks supervisor [-h]
                             {org-dashboard,ping,read-state,task-tracker} ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `supervisor org-dashboard`

Show org tree with status and tasks

`usage: animaworks supervisor org-dashboard [-h]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `supervisor ping`

Check if subordinate animas are alive

`usage: animaworks supervisor ping [-h] [--name NAME]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --name | option | — | — | Specific anima name (omit for all subordinates) |

## `supervisor read-state`

Read subordinate state (current_state.md, pending)

`usage: animaworks supervisor read-state [-h] name`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| name | positional | — | — | Target anima name |

## `supervisor task-tracker`

Track delegated tasks

`usage: animaworks supervisor task-tracker [-h] [--status STATUS]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --status | option | "delegated" | — | Filter by status (default: delegated) |

## `task`

Manage persistent task queue

`usage: animaworks task [-h]
                       {board,show,claim,release,done,cancel,note,add,update,resume,list}
                       ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `task add`

Add a new task

`usage: animaworks task add [-h] [--source {human,anima}] --instruction
                           INSTRUCTION --assignee ASSIGNEE [--summary SUMMARY]
                           [--relay-chain RELAY_CHAIN] [--workspace WORKSPACE]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --source | option | "anima" | human, anima | — |
| --instruction | option | — | — | Original instruction text |
| --assignee | option | — | — | Assignee anima name |
| --summary | option | — | — | 1-line summary (default: instruction[:100]) |
| --relay-chain | option | — | — | Comma-separated relay chain |
| --workspace | option | — | — | Workspace alias or path for the task's working_directory |

## `task board`

View and manage task board items.

`usage: animaworks task board [-h] [--anima ANIMA | --all] [--stale STALE]
                             [--limit LIMIT] [--json]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --anima | option | — | — | Show an owner's tasks and delegated work |
| --all | flag | false | — | Show all owners |
| --stale | option | — | — | Only tasks older than DAYS |
| --limit | option | 50 | — | Maximum rows (default: 50) |
| --json | flag | false | — | Emit JSON |

## `task cancel`

Cancel a task

`usage: animaworks task cancel [-h] --reason REASON [--json] task_id`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| task_id | positional | — | — | — |
| --reason | option | — | — | — |
| --json | flag | false | — | Emit JSON |

## `task claim`

Acquire a time-limited task lease

`usage: animaworks task claim [-h] [--ttl TTL] [--json] task_id`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| task_id | positional | — | — | — |
| --ttl | option | "30m" | — | Lease duration up to 4h (default: 30m) |
| --json | flag | false | — | Emit JSON |

## `task done`

Mark a task done

`usage: animaworks task done [-h] --note NOTE [--json] task_id`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| task_id | positional | — | — | — |
| --note | option | — | — | — |
| --json | flag | false | — | Emit JSON |

## `task list`

List tasks

`usage: animaworks task list [-h]
                            [--status {pending,in_progress,delegated,done,cancelled}]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --status | option | — | pending, in_progress, delegated, done, cancelled | — |

## `task note`

Append a note to a task

`usage: animaworks task note [-h] [--json] task_id text`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| task_id | positional | — | — | — |
| text | positional | — | — | — |
| --json | flag | false | — | Emit JSON |

## `task release`

Release your task lease

`usage: animaworks task release [-h] [--json] task_id`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| task_id | positional | — | — | — |
| --json | flag | false | — | Emit JSON |

## `task resume`

Requeue a task with its saved execution input

`usage: animaworks task resume [-h] --task-id TASK_ID`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --task-id | option | — | — | Task ID |

## `task show`

Show complete task details

`usage: animaworks task show [-h] [--anima ANIMA] [--json] task_id`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| task_id | positional | — | — | Task ID or delegator alias |
| --anima | option | — | — | Disambiguate by task owner |
| --json | flag | false | — | Emit JSON |

## `task update`

Update task status

`usage: animaworks task update [-h] --task-id TASK_ID --status
                              {pending,delegated,done,cancelled}
                              [--summary SUMMARY]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --task-id | option | — | — | Task ID |
| --status | option | — | pending, delegated, done, cancelled | — |
| --summary | option | — | — | Updated summary |

## `task-store`

Maintain and migrate per-assignee task source of truth

`usage: animaworks task-store [-h]
                             {status,quiesce,resume,migrate,backup,export} ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `task-store backup`

Create a new DB backup including WAL

`usage: animaworks task-store backup [-h] --anima ANIMA --destination
                                    DESTINATION`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --anima | option | — | — | Target assignee name |
| --destination | option | — | — | Unused output path |

## `task-store export`

Write the current shutdown state to a new directory

`usage: animaworks task-store export [-h] --anima ANIMA --destination
                                    DESTINATION`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --anima | option | — | — | Target assignee name |
| --destination | option | — | — | Unused output path |

## `task-store migrate`

Import a shutdown old ledger (backup required)

`usage: animaworks task-store migrate [-h] --anima ANIMA --backup BACKUP`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --anima | option | — | — | Target assignee name |
| --backup | option | — | — | Create a new DB backup including WAL |

## `task-store quiesce`

Permanently stop acquiring new executions

`usage: animaworks task-store quiesce [-h] --anima ANIMA`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --anima | option | — | — | Target assignee name |

## `task-store resume`

Resume fetching new runs

`usage: animaworks task-store resume [-h] --anima ANIMA`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --anima | option | — | — | Name of the target assignee |

## `task-store status`

Show shutdown gate and run count

`usage: animaworks task-store status [-h] --anima ANIMA`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --anima | option | — | — | Name of the target assignee |

## `tmp`

Inspect and clean AnimaWorks tmp directories

`usage: animaworks tmp [-h] {list,clean} ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `tmp clean`

Remove old or large tmp files

`usage: animaworks tmp clean [-h] [--older-than DAYS] [--min-size SIZE] [--all]
                            [--force] [--project] [--dry-run]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --older-than | option | 7 | — | Remove entries older than DAYS (default: 7) |
| --min-size | option | — | — | Also remove entries at or above SIZE (e.g. 100M, 1G) |
| --all | flag | false | — | Remove all entries under tmp (requires --force) |
| --force | flag | false | — | Required with --all for destructive full cleanup |
| --project | flag | false | — | Also clean repository tmp/ |
| --dry-run | flag | false | — | Show what would be removed without deleting |

## `tmp list`

Show tmp usage summary

`usage: animaworks tmp list [-h] [--project] [--top TOP]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --project | flag | false | — | Include repository tmp/ in addition to runtime tmp |
| --top | option | 20 | — | Maximum number of entries to show per root (default: 20) |

## `vault`

Manage encrypted vault values

`usage: animaworks vault [-h] {status,init,get,store,list,delete} ...`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `vault delete`

Remove a key from one section

`usage: animaworks vault delete [-h] [--shared] key`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| key | positional | — | — | Key to remove |
| --shared | flag | false | — | Delete from the shared section instead of the Anima namespace (never cascades) |

## `vault get`

Get a value by key

`usage: animaworks vault get [-h] [--shared] key`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| key | positional | — | — | Key to retrieve |
| --shared | flag | false | — | Look only in the shared section (default: Anima namespace, then shared) |

## `vault init`

Generate a vault key if one does not exist

`usage: animaworks vault init [-h]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `vault list`

List keys in the anima namespace and the shared section

`usage: animaworks vault list [-h] [--shared]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| --shared | flag | false | — | List only the shared section (does not require ANIMAWORKS_ANIMA_DIR) |

## `vault status`

Show key and encryption status without values

`usage: animaworks vault status [-h]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## `vault store`

Store a key-value pair

`usage: animaworks vault store [-h] [--shared] key [value]`

| Name | Type | Default | Choices | Description |
|---|---|---|---|---|
| key | positional | — | — | Key to store |
| value | positional | — | — | Value to store (Anima-scoped compatibility mode only) |
| --shared | flag | false | — | Store in the shared section, reading the value from stdin or a hidden prompt |
