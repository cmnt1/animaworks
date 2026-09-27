<!-- 自動生成ファイル・編集禁止。再生成: uv run python scripts/gen_reference.py tool-cli -->
<!-- generator: gen_reference/1  kind: tool-cli  source-sha256: 59025b6d1aec3b8d5ab07d6d1b6a17c85906b593b8d018cb21ba9f60b9316684 -->

# ツール CLI リファレンス: `animaworks-tool`

`animaworks-tool` は core の外部ツールスキーマから生成しています。common / personal tool は runtime 依存のため対象外です。

## `submit` によるバックグラウンド実行

`animaworks-tool submit <tool_name> [args...]` は長時間実行するツールを pending task として登録し、完了結果を inbox に届けます。実行には `ANIMAWORKS_ANIMA_DIR` が必要です。

## `discord_channel_post`

Post a message to a Discord text channel. The message appears with your Anima identity (name + avatar). Returns the message ID for future reference.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `channel_id` | string | はい | Discord channel ID |
| `text` | string | はい | Message text (Markdown supported, max 2000 chars) |

## `discord_unreplied`

Find Discord messages that mention your name but have not been replied to. Useful during heartbeat to check for pending requests.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `channel_id` | string | いいえ | Discord channel ID to search (optional — searches all cached channels if omitted) |
| `limit` | integer | いいえ | Maximum number of results (default: 10) |

## `google_sheets_append_values`

Append rows after the last data in a spreadsheet range/table (append_values). 上書きに注意。既存データ確認にはread_valuesを先に使う。

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `range` | string | はい | A1 range, optionally with sheet name (e.g. 'Sheet1!A1:C10') |
| `spreadsheet_id` | string | はい | Spreadsheet ID or full docs.google.com URL |
| `value_input_option` | string | いいえ | How input is interpreted: USER_ENTERED (default) or RAW |
| `values` | array | はい | 2D array of cell values (list of rows) |

## `google_sheets_read`

Read cell values from a spreadsheet range (read_values).

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `range` | string | いいえ | A1 range, optionally with sheet name (e.g. 'Sheet1!A1:C10') Default: A1:Z1000 |
| `spreadsheet_id` | string | はい | Spreadsheet ID or full docs.google.com URL |

## `google_sheets_tabs`

List sheet tabs and basic metadata of a spreadsheet (list_tabs).

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `spreadsheet_id` | string | はい | Spreadsheet ID or full docs.google.com URL |

## `google_sheets_write_values`

Overwrite cell values in a spreadsheet range (write_values). 上書きに注意。既存データ確認にはread_valuesを先に使う。

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `range` | string | はい | A1 range, optionally with sheet name (e.g. 'Sheet1!A1:C10') |
| `spreadsheet_id` | string | はい | Spreadsheet ID or full docs.google.com URL |
| `value_input_option` | string | いいえ | How input is interpreted: USER_ENTERED (default) or RAW |
| `values` | array | はい | 2D array of cell values (list of rows) |

## `slack_channel_post`

Post a message to an actual Slack channel via Bot Token API. Returns the message ts for future updates via slack_channel_update. Use this for external Slack channels (not internal Board).

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `channel_id` | string | はい | Slack channel ID (e.g. C0AJ4J5KK46) |
| `text` | string | はい | Message text (Markdown will be converted to Slack mrkdwn) |
| `thread_ts` | string | いいえ | Optional parent message ts to reply in-thread |

## `slack_channel_update`

Update an existing Slack message by ts. The message is silently replaced (no notification). Use this for live dashboards like task-board.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `channel_id` | string | はい | Slack channel ID |
| `text` | string | はい | New message text |
| `ts` | string | はい | Message timestamp to update (from slack_channel_post result) |
