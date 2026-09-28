<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/reference/tool-cli.md -->
<!-- i18n: source-sha256=2dd0bf986da2e5faac901c75f9ef3b0bda08cbfbe7cb2552c07e2a246dbb3261 generated=2026-09-27 engine=local model=deepseek-v4-flash translator=2 -->

# Tool CLI Reference: `animaworks-tool`

`animaworks-tool` is generated from the core external tool schema. Common / personal tools are excluded because they depend on the runtime.

## Background Execution with `submit`

`animaworks-tool submit <tool_name> [args...]` registers long-running tools as pending tasks and delivers the completion result to your inbox. Execution requires `ANIMAWORKS_ANIMA_DIR`.

## `discord_channel_post`

Post a message to a Discord text channel. The message appears with your Anima identity (name + avatar). Returns the message ID for future reference.

| Argument | Type | Required | Description |
|---|---|---|---|
| `channel_id` | string | Yes | Discord channel ID |
| `text` | string | Yes | Message text (Markdown supported, max 2000 chars) |

## `discord_unreplied`

Find Discord messages that mention your name but have not been replied to. Useful during heartbeat to check for pending requests.

| Argument | Type | Required | Description |
|---|---|---|---|
| `channel_id` | string | No | Discord channel ID to search (optional — searches all cached channels if omitted) |
| `limit` | integer | No | Maximum number of results (default: 10) |

## `google_sheets_append_values`

Append rows after the last data in a spreadsheet range/table (append_values). Be careful about overwriting. Use read_values first to check existing data.

| Argument | Type | Required | Description |
|---|---|---|---|
| `range` | string | Yes | A1 range, optionally with sheet name (e.g. 'Sheet1!A1:C10') |
| `spreadsheet_id` | string | Yes | Spreadsheet ID or full docs.google.com URL |
| `value_input_option` | string | No | How input is interpreted: USER_ENTERED (default) or RAW |
| `values` | array | Yes | 2D array of cell values (list of rows) |

## `google_sheets_read`

Read cell values from a spreadsheet range (read_values).

| Argument | Type | Required | Description |
|---|---|---|---|
| `range` | string | No | A1 range, optionally with sheet name (e.g. 'Sheet1!A1:C10') Default: A1:Z1000 |
| `spreadsheet_id` | string | Yes | Spreadsheet ID or full docs.google.com URL |

## `google_sheets_tabs`

List sheet tabs and basic metadata of a spreadsheet (list_tabs).

| Argument | Type | Required | Description |
|---|---|---|---|
| `spreadsheet_id` | string | Yes | Spreadsheet ID or full docs.google.com URL |

## `google_sheets_write_values`

Overwrite cell values in a spreadsheet range (write_values). Be careful about overwriting. Use read_values first to check existing data.

| Argument | Type | Required | Description |
|---|---|---|---|
| `range` | string | Yes | A1 range, optionally with sheet name (e.g. 'Sheet1!A1:C10') |
| `spreadsheet_id` | string | Yes | Spreadsheet ID or full docs.google.com URL |
| `value_input_option` | string | No | How input is interpreted: USER_ENTERED (default) or RAW |
| `values` | array | Yes | 2D array of cell values (list of rows) |

## `slack_channel_post`

Post a message to an actual Slack channel via Bot Token API. Returns the message ts for future updates via slack_channel_update. Use this for external Slack channels (not internal Board).

| Argument | Type | Required | Description |
|---|---|---|---|
| `channel_id` | string | Yes | Slack channel ID (e.g. C0AJ4J5KK46) |
| `text` | string | Yes | Message text (Markdown will be converted to Slack mrkdwn) |
| `thread_ts` | string | No | Optional parent message ts to reply in-thread |

## `slack_channel_update`

Update an existing Slack message by ts. The message is silently replaced (no notification). Use this for live dashboards like task-board.

| Argument | Type | Required | Description |
|---|---|---|---|
| `channel_id` | string | Yes | Slack channel ID |
| `text` | string | Yes | New message text |
| `ts` | string | Yes | Message timestamp to update (from slack_channel_post result) |
