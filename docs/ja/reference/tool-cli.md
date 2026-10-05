<!-- 自動生成ファイル・編集禁止。再生成: uv run python scripts/gen_reference.py tool-cli -->
<!-- generator: gen_reference/1  kind: tool-cli  source-sha256: 118ed29fc876a51d7dc2a00f2502b067f6abba53b8f030b249dcea01b3bad002 -->

# ツール CLI リファレンス: `animaworks-tool`

`animaworks-tool` は core の外部ツールスキーマから生成しています。common / personal tool は runtime 依存のため対象外です。

## `submit` によるバックグラウンド実行

`animaworks-tool submit <tool_name> [args...]` は長時間実行するツールを pending task として登録し、完了結果を inbox に届けます。実行には `ANIMAWORKS_ANIMA_DIR` が必要です。

## `bluesky_author_feed`

Fetch recent public Bluesky posts from a handle or DID.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `actor` | string | はい | Bluesky handle or DID. |
| `include_replies` | boolean | いいえ | Include replies and threads. Default: false. |
| `limit` | integer | いいえ | Maximum posts to return, 1-100. Default: 25. |

## `bluesky_search`

Search public Bluesky posts via the Bluesky AppView API. Useful for market chatter, company/ticker mentions, and news discussion signals.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `author` | string | いいえ | Optional author handle without or with @. |
| `lang` | string | いいえ | Optional language code, e.g. ja or en. |
| `limit` | integer | いいえ | Maximum posts to return, 1-100. Default: 25. |
| `query` | string | はい | Search query string. |
| `since` | string | いいえ | Optional ISO datetime lower bound. |
| `sort` | string | いいえ | Sort mode. Default: latest. |
| `tag` | string | いいえ | Optional hashtag without or with #. |
| `until` | string | いいえ | Optional ISO datetime upper bound. |

## `discord_channel_post`

Post a message to a Discord text channel. The message appears with your Anima identity (name + avatar). Returns the message ID for future reference.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `channel_id` | string | はい | Discord parent channel ID. When replying into a thread, this MUST be the parent text channel ID (not the thread ID) — Discord webhooks are attached to the parent channel and target the thread via the separate thread_id parameter. |
| `text` | string | はい | Message text (Markdown supported, max 2000 chars) |
| `thread_id` | string | いいえ | Thread channel ID to post into. REQUIRED when replying to a message that arrived from within a thread — otherwise the post lands in the parent channel. Use the value shown in the [reply_instruction: ...] annotation of the incoming message. |

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

## `notebooklm_add_source_file`

Add a local file (PDF, DOCX, MD, CSV, etc.) as a source to a NotebookLM notebook.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `file_path` | string | はい | Absolute path to the file |
| `notebook_id` | string | はい | Notebook ID |

## `notebooklm_add_source_text`

Add pasted text as a source to a NotebookLM notebook.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `notebook_id` | string | はい | Notebook ID |
| `text` | string | はい | Text content to add |
| `title` | string | いいえ | Optional title for the source |

## `notebooklm_add_source_url`

Add a web page URL as a source to a NotebookLM notebook.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `notebook_id` | string | はい | Notebook ID |
| `url` | string | はい | Web page URL to add |

## `notebooklm_chat`

Ask a question against the sources in a NotebookLM notebook. Returns an answer with source references.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `message` | string | はい | Question to ask |
| `notebook_id` | string | はい | Notebook ID |

## `notebooklm_create_notebook`

Create a new Google NotebookLM notebook.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `title` | string | はい | Notebook title |

## `notebooklm_delete_notebook`

Delete a Google NotebookLM notebook.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `notebook_id` | string | はい | Notebook ID |

## `notebooklm_generate_artifact`

Generate an artifact from a NotebookLM notebook. Types: audio_overview, briefing_doc, study_guide, faq, timeline, mind_map. Long-running — use 'animaworks-tool submit' for background execution.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `artifact_type` | string | はい | Type of artifact to generate |
| `instructions` | string | いいえ | Custom instructions for generation |
| `language` | string | いいえ | Output language (default: en) |
| `notebook_id` | string | はい | Notebook ID |

## `notebooklm_get_notebook`

Get a NotebookLM notebook's summary, description, and topics.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `notebook_id` | string | はい | Notebook ID |

## `notebooklm_get_source_fulltext`

Get the full text content of a source in a NotebookLM notebook.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `notebook_id` | string | はい | Notebook ID |
| `source_id` | string | はい | Source ID (from notebooklm_list_sources) |

## `notebooklm_list_artifacts`

List artifacts in a NotebookLM notebook.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `artifact_type` | string | いいえ | Filter by type (e.g. AUDIO, REPORT, MIND_MAP) |
| `notebook_id` | string | はい | Notebook ID |

## `notebooklm_list_notebooks`

List all Google NotebookLM notebooks.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| — | — | — | — |

## `notebooklm_list_sources`

List all sources in a NotebookLM notebook.

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `notebook_id` | string | はい | Notebook ID |

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
