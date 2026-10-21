<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/reference/tool-cli.md -->
<!-- i18n: source-sha256=70a59165699d3f658dee8a9762c751fad73d0048acdadd4bbe79a622aebddb1b generated=2026-10-21 engine=nanogpt model=deepseek/deepseek-v4.1-flash translator=2 -->

# Tool CLI Reference: `animaworks-tool`

`animaworks-tool` is generated from the core external tool schema. Common and personal tools are excluded because they depend on the runtime.

## Background Execution with `submit`

`animaworks-tool submit <tool_name> [args...]` registers long-running tools as pending tasks and delivers completion results to the inbox. Execution requires `ANIMAWORKS_ANIMA_DIR`.

## `bluesky_author_feed`

Fetch recent public Bluesky posts from a handle or DID.

| Argument | Type | Required | Description |
|---|---|---|---|
| `actor` | string | Yes | Bluesky handle or DID. |
| `include_replies` | boolean | No | Include replies and threads. Default: false. |
| `limit` | integer | No | Maximum posts to return, 1-100. Default: 25. |

## `bluesky_search`

Search public Bluesky posts via the Bluesky AppView API. Useful for market chatter, company/ticker mentions, and news discussion signals.

| Argument | Type | Required | Description |
|---|---|---|---|
| `author` | string | No | Optional author handle without or with @. |
| `lang` | string | No | Optional language code, e.g. ja or en. |
| `limit` | integer | No | Maximum posts to return, 1-100. Default: 25. |
| `query` | string | Yes | Search query string. |
| `since` | string | No | Optional ISO datetime lower bound. |
| `sort` | string | No | Sort mode. Default: latest. |
| `tag` | string | No | Optional hashtag without or with #. |
| `until` | string | No | Optional ISO datetime upper bound. |

## `discord_channel_post`

Post a message to a Discord text channel. The message appears with your Anima identity (name + avatar). Returns the message ID for future reference.

| Argument | Type | Required | Description |
|---|---|---|---|
| `channel_id` | string | Yes | Discord parent channel ID. When replying into a thread, this MUST be the parent text channel ID (not the thread ID) — Discord webhooks are attached to the parent channel and target the thread via the separate thread_id parameter. |
| `text` | string | Yes | Message text (Markdown supported, max 2000 chars) |
| `thread_id` | string | No | Thread channel ID to post into. REQUIRED when replying to a message that arrived from within a thread — otherwise the post lands in the parent channel. Use the value shown in the [reply_instruction: ...] annotation of the incoming message. |

## `discord_unreplied`

Find Discord messages that mention your name but have not been replied to. Useful during heartbeat to check for pending requests.

| Argument | Type | Required | Description |
|---|---|---|---|
| `channel_id` | string | No | Discord channel ID to search (optional — searches all cached channels if omitted) |
| `limit` | integer | No | Maximum number of results (default: 10) |

## `enclave_ask`

Send a question to an isolated enclave and immediately receive a job_id. You can check the status, and the completion result will arrive in your inbox.

| Argument | Type | Required | Description |
|---|---|---|---|
| `case_id` | string | No | Optional case identifier (generated from the anima name and date if omitted) |
| `enclave` | string | Yes | Configuration name of the enclave to connect to |
| `model` | string | No | Optional model specification (the name of a model_profiles entry on the enclave, e.g., luna-max / opus-high. Defaults to the enclave's default if omitted) |
| `question` | string | Yes | Question to send to the isolated instance |
| `wait_s` | integer | No | Maximum number of seconds to wait before checking the result (default: 0. Returns immediately when set to 0) |

## `enclave_cancel`

Cancel a running or queued enclave job.

| Argument | Type | Required | Description |
|---|---|---|---|
| `enclave` | string | Yes | Configuration name of the enclave to connect to |
| `job_id` | string | Yes | Job ID returned by enclave ask |

## `enclave_status`

Check an enclave job's status, elapsed time, progress updates, and facts upon completion.

| Argument | Type | Required | Description |
|---|---|---|---|
| `enclave` | string | Yes | Configuration name of the enclave to connect to |
| `job_id` | string | Yes | Job ID returned by enclave ask |

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

## `notebooklm_add_source_file`

Add a local file (PDF, DOCX, MD, CSV, etc.) as a source to a NotebookLM notebook.

| Argument | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | Yes | Absolute path to the file |
| `notebook_id` | string | Yes | Notebook ID |

## `notebooklm_add_source_text`

Add pasted text as a source to a NotebookLM notebook.

| Argument | Type | Required | Description |
|---|---|---|---|
| `notebook_id` | string | Yes | Notebook ID |
| `text` | string | Yes | Text content to add |
| `title` | string | No | Optional title for the source |

## `notebooklm_add_source_url`

Add a web page URL as a source to a NotebookLM notebook.

| Argument | Type | Required | Description |
|---|---|---|---|
| `notebook_id` | string | Yes | Notebook ID |
| `url` | string | Yes | Web page URL to add |

## `notebooklm_chat`

Ask a question against the sources in a NotebookLM notebook. Returns an answer with source references.

| Argument | Type | Required | Description |
|---|---|---|---|
| `message` | string | Yes | Question to ask |
| `notebook_id` | string | Yes | Notebook ID |

## `notebooklm_create_notebook`

Create a new Google NotebookLM notebook.

| Argument | Type | Required | Description |
|---|---|---|---|
| `title` | string | Yes | Notebook title |

## `notebooklm_delete_notebook`

Delete a Google NotebookLM notebook.

| Argument | Type | Required | Description |
|---|---|---|---|
| `notebook_id` | string | Yes | Notebook ID |

## `notebooklm_generate_artifact`

Generate an artifact from a NotebookLM notebook. Types: audio_overview, briefing_doc, study_guide, faq, timeline, mind_map. Long-running — use 'animaworks-tool submit' for background execution.

| Argument | Type | Required | Description |
|---|---|---|---|
| `artifact_type` | string | Yes | Type of artifact to generate |
| `instructions` | string | No | Custom instructions for generation |
| `language` | string | No | Output language (default: en) |
| `notebook_id` | string | Yes | Notebook ID |

## `notebooklm_get_notebook`

Get a NotebookLM notebook's summary, description, and topics.

| Argument | Type | Required | Description |
|---|---|---|---|
| `notebook_id` | string | Yes | Notebook ID |

## `notebooklm_get_source_fulltext`

Get the full text content of a source in a NotebookLM notebook.

| Argument | Type | Required | Description |
|---|---|---|---|
| `notebook_id` | string | Yes | Notebook ID |
| `source_id` | string | Yes | Source ID (from notebooklm_list_sources) |

## `notebooklm_list_artifacts`

List artifacts in a NotebookLM notebook.

| Argument | Type | Required | Description |
|---|---|---|---|
| `artifact_type` | string | No | Filter by type (e.g. AUDIO, REPORT, MIND_MAP) |
| `notebook_id` | string | Yes | Notebook ID |

## `notebooklm_list_notebooks`

List all Google NotebookLM notebooks.

| Argument | Type | Required | Description |
|---|---|---|---|
| — | — | — | — |

## `notebooklm_list_sources`

List all sources in a NotebookLM notebook.

| Argument | Type | Required | Description |
|---|---|---|---|
| `notebook_id` | string | Yes | Notebook ID |

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
