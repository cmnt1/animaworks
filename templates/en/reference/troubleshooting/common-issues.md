# Common Problems and Solutions

A reference compiling problems frequently encountered during work and their resolution procedures.
Each problem is documented in the format "Symptom → Cause → Resolution Procedure."

When in trouble, first read this documentation and follow the procedure for the relevant item.
If the issue is not resolved here, refer to `troubleshooting/escalation-flowchart.md` and escalate appropriately.

---

## Messages Not Being Delivered

### Symptoms

- No response to a message that was sent
- The recipient says the message was not received
- Executed `send_message`, but the recipient did not respond

### Causes

1. Incorrect destination specification (Anima official name, user alias, `slack:` / `chatwork:` prefix, etc.) or a specification that does not match the resolution order
2. The server is down
3. The recipient is between heartbeat intervals (messages remain unread until the next startup)
4. The send process failed with an error (global send limit, conversation depth limit, in-session DM limit, `RecipientResolutionError`, etc.)
5. `intent` is unspecified or invalid. For DMs, only `report` / `question` are allowed. For task delegation, use `delegate_task` (attaching `intent="delegation"` to `send_message` returns a deprecation message)
6. In-session DM limit exceeded (**only 1 message per session to the same destination**. **The maximum number of distinct destinations** is `max_recipients_per_run` according to `role` in `status.json` — see table below. Individual overrides are available via the same-named field in `status.json`)

**`max_recipients_per_run` by role (`core/config/schemas.py` `ROLE_OUTBOUND_DEFAULTS`)**

| role | Maximum destinations per session (1 message each) |
|------|--------------------------------------|
| manager | 10 |
| engineer | 5 |
| writer | 3 |
| researcher | 3 |
| ops | 2 |
| general | 2 |

### Resolution Procedure

1. **Verify the recipient name and destination format**
   - Confirm that the `to` parameter of `send_message` resolves to the intended recipient
   - The resolution order of the implementation (`core/messaging/outbound.py` `resolve_recipient`) is roughly as follows:
     1. **Exact match** with a known Anima name (case-sensitive) → internal
     2. **Alias** of `config.json` `external_messaging.user_aliases` (case-insensitive) → external (preferred_channel)
     3. `slack:USERID` / `chatwork:ROOMID` → external direct
     4. Bare Slack user ID (`U` + 8 or more alphanumeric characters) → Slack direct
     5. **Case-insensitive match** with a known Anima name → internal
     6. Anything else → resolution failure
   - To reliably reach an internal Anima, use the **official name** on `~/.animaworks/animas/<名前>/` or `reference/organization/structure.md`
   - How to verify:
     ```
     search_memory(query="組織", scope="common_knowledge")
     ```
     Or check all Anima names in the organization via `read_memory_file(path="reference/organization/structure.md")`
   - **Note**: In chat, `send_message` cannot be used for human recipients. Respond directly with text to reach a human. When contacting a human outside of chat (e.g., heartbeat), use `call_human`

2. **Check the server status**
   - Since you are running, the server should be operational
   - If still concerned, report to your supervisor that "messages are not being delivered"

3. **Wait for the recipient's response**
   - The recipient checks their inbox at heartbeat intervals (e.g., every 30 minutes)
   - Even without an immediate reply, it will be processed at the next heartbeat
   - In urgent cases, report to your supervisor that "I need to make contact urgently" and request a manual startup

4. **If a send error occurred**
   - Record the error message
   - Document the situation in `state/current_state.md`
   - Report to your supervisor

### Specific Examples

```
# 名前を間違えていた場合
send_message(to="Aoi", content="...", intent="report")   # OK
send_message(to="aoi", content="...", intent="report")  # 名前が異なればエラーになる可能性あり

# DM は intent 必須（report / question のみ）。委譲は delegate_task
# 1セッションあたりの「別宛先」数はロールにより異なる（例: general は最大2人、engineer は5人まで）。同一宛先へは1回のみ
send_message(
    to="aoi",
    content="了解しました。作業を開始します。",
    intent="report",           # 必須: report / question
    reply_to="msg-abc123",     # 任意: 元メッセージのID
    thread_id="thread-xyz789"  # 任意: スレッドID
)

# 確認・お礼・お知らせのみのDMは不可 → post_channel（Board）を使用
```

---

## Unable to Proceed with a Task

There is no state of "waiting until conditions are met" or "blocked" (`blocked` has been deprecated). You can only choose among three options: proceed, close, or consult.

### Symptoms

- Tried to proceed with work but lacked the necessary information or permission
- Waiting for another Anima to complete their work
- An external service returns an error

### Causes

1. Dependent tasks are incomplete
2. Insufficient permission (an operation not allowed by `permissions.json`. Even in an environment with only `permissions.md`, the first `load_permissions` generates JSON and the MD is moved to `.bak`)
3. Necessary information is missing
4. External service outage

### Resolution Procedure

1. **Do not repeat the same operation**
   - Specifically identify what is missing
   - Clarify "whose," "what work," and "by when" is needed

2. **Determine whether you can resolve it yourself**
   - Consider whether a different approach can work around the issue
   - Search your memory to check whether a similar problem occurred in the past:
     ```
     search_memory(query="エラー内容やキーワード", scope="episodes")
     search_memory(query="回避", scope="knowledge")
     ```

3. **If you cannot resolve it, report to the requester** (see `troubleshooting/escalation-flowchart.md`). The report should include:
   - What you attempted to do
   - What is missing or what you are waiting for
   - What you tried yourself and your recommendation
   ```
   send_message(
       to="上司の名前",
       content="【進捗報告】\nタスク: XXXの実装\n事実: YYYのAPI権限が不足\n試行: permissions.jsonを確認したが該当設定なし\n推奨: API権限の追加をお願いします",
       intent="report"
   )
   ```

4. **Decide how to handle the task**
   - If there is a possibility of continuing, you may do nothing (the task remains in `pending`. Even if the session ends without a declaration, it automatically returns to `pending`)
   - If it is no longer needed, set it to `update_task(status="cancelled", summary="理由")`

5. **Check whether there is other work you can do while waiting**
   - Persistent task queue: if the tool is available, check via `list_tasks` or `Bash: animaworks-tool task list`
   - Use `list_tasks(detail=true)` to check unstarted tasks, dependencies, and reasons requiring action. Do not duplicate existing tasks or manually re-submit them
   - Start another task

---

## Memory Not Found

### Symptoms

- Cannot recall something done in the past
- A procedure document should exist but cannot be found
- Searches return no relevant results

### Causes

1. Search keywords are not appropriate
2. The search scope is too narrow
3. The information has not yet been written to memory (first-time work)
4. The file path is incorrect

### Handling Procedure

1. **Broaden the scope and search again**
   - First, search broadly with the `all` scope:
     ```
     search_memory(query="keyword to search", scope="all")
     ```
   - If there are too many results, narrow the scope:
     ```
     search_memory(query="Slack configuration", scope="procedures")    # Limited to procedure documents
     search_memory(query="Slack incident", scope="episodes")          # Limited to past events
     search_memory(query="Slack", scope="knowledge")                 # Limited to learned knowledge
     ```

2. **Change the keywords and search again**
   - Try synonyms and related terms (e.g., "send", "message", "notification", "contact")
   - Also try English keywords (e.g., "slack", "message", "send")
   - Be mindful of partial matches (e.g., "Chatwork" → "chatwork", "チャットワーク")

3. **Search shared knowledge**
   - If it is not in personal memory, it may exist in shared knowledge:
     ```
     search_memory(query="search keyword", scope="common_knowledge")
     ```
   - Check the table of contents of shared knowledge:
     ```
     read_memory_file(path="common_knowledge/00_index.md")
     ```

4. **Check the directory directly**
   - In Mode S (Claude Agent SDK) and similar, the built-in `Glob` can list the contents under the Anima directory. In Mode A and similar, use `read_memory_file` to open known paths, or use `search_memory` to search broadly
   - If the file name is known, read it directly:
     ```
     read_memory_file(path="procedures/slack-setup.md")
     read_memory_file(path="knowledge/xxx-findings.md")
     ```

5. **If the memory does not exist**
   - It may be a first-time task
   - Check whether shared knowledge (`common_knowledge/`) contains any relevant guides
   - Ask supervisors or colleagues whether they have any insights
   - After completion of the task, record it as memory using MUST (for next time)
   - Old or duplicate memories can be moved to archive/ using `archive_memory_file(path="...", reason="...")` (move, not delete; `reason` is required)### Search Scope List

| scope | Search target | Use case |
|-------|---------|------|
| `knowledge` | Learned knowledge and know-how | Response policies, technical notes |
| `episodes` | Past action logs | Fact-checking "what was done when" |
| `procedures` | Procedure documents | Confirming "how to do" procedures |
| `common_knowledge` | Knowledge shared by all Anima | Organizational rules, system guides |
| `skills` | Skills and common skills (vector search) | Skill discovery and search |
| `activity_log` | Recent action logs (tool execution results, messages, etc.) | Fact-checking recent items such as "the email I just read" or "the previous search results" |
| `all` | All of the above (vector search + activity_log BM25 integrated via RRF) | Keyword existence checks, broad searches |

---

## No Permission

### Symptoms

- An error such as "Permission denied" was returned when running the tool
- Attempted to read or write a file but could not access it
- Attempted to run a command but it was rejected### Causes

1. An operation not allowed by `permissions.json` (if only `permissions.md` is present, `load_permissions` is normalized to JSON-equivalent on read. Invalid JSON may fall back to open defaults with a warning)
2. The external tool category is not enabled in the registry (`available_but_not_enabled` of `check_permissions`)
3. The file path is outside the allowed range (writing to protected files, outside `file_roots`, etc.). Additionally, **global** denials exist in both `permissions.global.json` and framework-side patterns

### 対処手順

1. **自分の権限を確認する**
   ```
   check_permissions()
   ```
   - JSON で返る。`internal_tools`・`external_tools.enabled` / `available_but_not_enabled`・`file_access`（read/write）・`restrictions`（コマンド deny 等）を確認する
   - 生の設定は `read_memory_file(path="permissions.json")`（存在しない場合は `permissions.md`）で確認可能
   - システムプロンプトに注入される権限説明は、ランタイムが JSON から整形したテキストになる

2. **許可されている操作か確認する**
   - 自分の `anima_dir` 内は原則読み書き可能（`identity.md` 等の保護ファイルは除く）。上司・同僚の `activity_log` や配下の `state/` 読み取りはロール次第で `check_permissions` の `file_access` に反映される
   - シェルコマンド: `permissions.json` の `commands`（allow/deny）に従う。グローバル危険パターンはフレームワーク側でもブロックされる

3. **権限が必要な場合の対応**
   - その操作が本当に必要か再検討する
   - 別のアプローチ（許可された範囲内の操作）で代替できないか考える
   - 代替不可能な場合は上司に権限追加を依頼する:
   ```
   send_message(
       to="上司の名前",
       content="【権限追加依頼】\n目的: XXXの作業のため\n必要な権限: /path/to/dir の読み取り\n理由: YYYの情報を参照する必要があるため",
       intent="question"
   )
   ```

4. **絶対にやってはいけないこと**
   - 権限チェックを回避しようとすること
   - 許可されていないコマンドを別の方法で実行しようとすること
   - 他のAnimaの権限を利用しようとすること

---

## Tools Unavailable

### Symptoms

- An error such as "Tool not found" was returned when calling a tool
- External tools (Slack, Gmail, etc.) are unavailable### Cause

1. The tool is not permitted in `permissions.json` (or the normalized MD-derived configuration at load time), or gated actions are not explicitly permitted
2. The skill file is not found
3. Authentication information for the external service is not configured

### Resolution Steps

1. **Check how to use the tool in the skill**
   - Specify the path shown in the skill catalog of the system prompt with `read_memory_file` (e.g., `skills/foo/SKILL.md`, `common_skills/bar/SKILL.md`) and retrieve the full procedure
   - If external tools are permitted in B-mode, they can be called with `Bash: animaworks-tool <ツール> <サブコマンド>`

2. **Check permissions**
   ```
   check_permissions()
   ```
   - `external_tools.enabled`: External tool categories registered in this Anima's tool registry (those actually passed to the session)
   - `external_tools.available_but_not_enabled`: Categories implemented in the framework but not in this Anima's registry. Check together with the permissions, gated actions, and execution mode in `permissions.json`

3. **If unavailable**
   - Check with `permissions.json` whether the relevant tool/action is permitted and whether authentication information (e.g., `shared/credentials.json`) exists
   - If still not possible, request from the supervisor (clearly stating "why this tool is needed")

4. **For MCP integration mode (S/C/D/G: Claude Agent SDK / Codex CLI / Cursor Agent / Gemini CLI)**
   - Built-in tools are available without a prefix (e.g., `send_message`). If not found, a process restart is required
   - For external tools, read the skill text with `read_memory_file` to check CLI usage, and execute `animaworks-tool <ツール> <サブコマンド>` via **Bash** (using the agent's Bash tool)
   - Long-running tools (image generation, local LLM, etc.) are executed asynchronously with `animaworks-tool submit`

5. **Common issues specific to D-mode (Cursor Agent)**
   - **CLI not found**: Check whether the `cursor-agent` CLI is installed on the host
   - **Authentication error**: Run `agent login` in the terminal to log in
   - **Fallback**: If unresolved, set `execution_mode` to `A`, or switch the model to LiteLLM (Mode A) for operation

6. **Common issues specific to G-mode (Gemini CLI)**
   - **CLI not found**: Check whether the `gemini` CLI is installed on the host
   - **Authentication error**: Run `gemini auth login` or set the environment variable `GEMINI_API_KEY`
   - **Fallback**: If unresolved, set `execution_mode` to `A`, or switch the model to LiteLLM (Mode A). The `gemini/` prefix may be remapped to `google/` for Google providers

7. **For A-mode (LiteLLM)**
   - For external tools, read the skill text with `read_memory_file` to check usage, and execute `animaworks-tool <ツール> <サブコマンド>` via **Bash**

8. **If the tool returns an error**
   - Record the error message accurately
   - If it is an authentication error, report to the supervisor (authentication configuration is the administrator's responsibility)
   - If it is a temporary timeout or rate limit, wait briefly and retry (the number and interval depend on the tool implementation and server configuration)
   - If it does not improve, report the facts and what was tried to the requester

For the overall tool architecture, see `operations/tool-usage-overview.md`.

---

## Context has become too long

### Symptoms

- The session has been running for a long time
- Responses have become slower
- A notification from the system indicates "approaching the context limit"

### Cause

- Long-running work or numerous tool calls have consumed the context window
- Large amounts of file content were loaded

### Resolution Steps

1. **Save the work status to short-term memory** (MUST)
   - Write the current work status to `shortterm/` (or `shortterm/chat/` during chat sessions):
   ```
   write_memory_file(
       path="shortterm/chat/session_state.md",
       content="## 作業状態\n\n### 実行中のタスク\n- XXXの実装（50%完了）\n\n### 次のステップ\n1. YYYを完了する\n2. ZZZをテストする\n\n### 重要な中間結果\n- AAAの調査結果: BBB\n- CCCの設定値: DDD",
       mode="overwrite"
   )
   ```
   - For heartbeat sessions, use `shortterm/heartbeat/session_state.md`

2. **Update `state/current_state.md`** (MUST)
   ```
   write_memory_file(
       path="state/current_state.md",
       content="## 現在のタスク\n\nXXXの実装\n\n### 進捗\n- 50%完了\n- 次回はYYYから再開\n\n### メモ\n- 重要な発見事項をここに記載",
       mode="overwrite"
   )
   ```

3. **Save important insights to persistent memory** (SHOULD)
   - Save insights gained during work to `knowledge/`:
   ```
   write_memory_file(
       path="knowledge/xxx-findings.md",
       content="# XXXに関する知見\n\n## 発見事項\n...",
       mode="overwrite"
   )
   ```

4. **Wait for the session to continue**
   - The system will automatically start a new session
   - In the new session, the contents of `shortterm/chat/` (or `shortterm/heartbeat/`) are included in the context
   - Re-read `state/current_state.md` to resume work

### Preventive Measures

- For large files, do not read the entire file; search only for the necessary parts
- For long tasks, update `state/current_state.md` regularly
- Write intermediate results to memory frequently

---

## Message sending was restricted

### Symptoms

- An error was returned when executing `send_message` or `post_channel`
- `GlobalOutboundLimitExceeded: 1時間あたりの送信上限（N通）に到達しています...` or a similar 24-hour message was displayed
- `GlobalOutboundLimitExceeded: アクティビティログ読み取り失敗のため送信をブロックしました` was displayed (`core/messaging/cascade_limiter.py` — when the sender's `activity_log` cannot be read)
- `ConversationDepthExceeded: {相手}との会話が10分間に6ターンに達しました...` was displayed

### Cause

- **Per-role global limit**: `dm_sent` / `message_sent` / `channel_post` are aggregated from activity_log and judged by the 1-hour and 24-hour counts (`ConversationDepthLimiter.check_global_outbound`). The limit can be individually overridden with `max_outbound_per_hour` / `max_outbound_per_day` in `status.json`; if not set, the default in `role` (`ROLE_OUTBOUND_DEFAULTS`) is used

**Per-role 1-hour / 24-hour limits (code defaults)**

| role | 1 hour | 24 hours |
|------|--------|----------|
| manager | 60 | 300 |
| engineer | 40 | 200 |
| writer | 30 | 150 |
| researcher | 30 | 150 |
| ops | 20 | 80 |
| general | 15 | 50 |

- Consecutive posts to the same channel were within the cooldown period (`config.json` `heartbeat.channel_post_cooldown_s`, default 300 seconds)
- The back-and-forth between two parties exceeded the depth limit (`ConversationDepthLimiter.check_depth` in `Messenger.send`. **Only DMs addressed to internal Anima** are subject. `heartbeat.depth_window_s` / `heartbeat.max_depth`, default **600 seconds** and **maximum 6 turns**. The wording is "10 minutes, 6 turns")
- Activity log read error (disk, permission, corruption, etc.) → send blocked on the safe side

### Resolution Steps

1. **Check the error message**: Identify whether it is a time limit, 24-hour limit, depth limit, or activity_log failure
2. **Review the send history**: Check whether there were any unnecessary sends
3. **Wait**: For time limits, wait until the next 1-hour window (the message may include "approximate next send time"); for 24-hour limits, wait until the next day; for depth limits, wait until the window opens
4. **Record the send content**: When the limit is reached, follow the message instructions: do not use `send_message` this turn, write to `state/current_state.md`, and send in the next session
5. **For activity_log failure**: Ask the administrator to check the log, disk, and `activity_log/` of the relevant Anima (the block depends on the sender's log read)
6. **Emergency contact**: `call_human` is not subject to these global limits
7. **Consolidate sends**: Combine multiple reports into one message. If the depth limit is reached, move to the Board (`post_channel`)

For details, see `communication/sending-limits.md`.

---

## Command was blocked

### Symptoms

- An error such as "PermissionDenied" or "Command blocked" was returned when trying to execute a command
- Only specific commands cannot be executed

### Cause

1. Commands matching the global deny patterns of the framework/`permissions.global.json` (e.g., `rm -rf /`, etc.)
2. Commands listed in `commands.deny` of `permissions.json`

### Resolution Steps

1. **Check your own permissions**
   ```
   check_permissions()
   ```
   - Denied commands are listed in `restrictions`. Also check the configuration directly with `read_memory_file(path="permissions.json")` (in legacy environments, `permissions.md`)

2. **Consider alternatives**
   - Consider whether the same operation as the blocked command can be achieved with permitted tools
   - Example: If `rm -rf` is blocked, deleting individual files may still be permitted

3. **If permission changes are needed**
   - Request unblocking from the supervisor
   - When requesting, clearly state "why this command is needed"

---

## Prompt was shortened

### Symptoms

- The system prompt is thinner than usual, and Priming (automatic recall) is nearly empty
- After long conversations or large user messages, behavior suggests the prompt was rebuilt before responding

### Cause

There are two main layers.

**1. Priming (automatic recall) tiers** — `resolve_prompt_tier(context_window)` in `core/prompt/builder.py` determines the tier from the estimated context window. The window resolution order is `core/prompt/context.py` `resolve_context_window`: **`~/.animaworks/models.json` (SSoT)** → deprecated `config.json` `model_context_windows` → code fallback such as `MODEL_CONTEXT_WINDOWS` → default 128k.

| Tier | Condition (`context_window`) | Priming handling (`core/agent/priming.py`) |
|------|--------------------------|---------------------------------------------|
| full | **≥ 128_000** | Format 6 channels with `format_priming_section` and include as-is |
| standard | **≥ 32_000 and < 128_000** | Retrieve as above, but **if the formatted text exceeds 4000 characters, use the first 4000 characters + an ellipsis marker** |
| light | **≥ 16_000 and < 32_000** | **Sender profile (Channel A) only** (with i18n header). Other channels are discarded |
| minimal | **< 16_000** | **Skip Priming entirely** (empty string) |

The query text for heartbeat/cron is a text assembled from the most recent `[REFLECTION]` in activity_log (not the full long template).

**2. System prompt body contraction** — `core/agent/priming.py` `_fit_prompt_to_context_window`: When the estimated tokens of system + user plus tool schema overhead exceed **approximately 80% of the context window**, `build_system_prompt` is rebuilt by progressively reducing the **system budget from 75% → 50% → 25%**. At the **25% or lower stage**, the **Priming block and the human notification block are emptied** before applying. If it still does not fit, the system prompt is **hard-truncated at the byte level**.

### Resolution Steps

1. **Explicitly retrieve missing context**: Read organization, procedures, and shared knowledge with `search_memory` / `read_memory_file` (especially in `minimal` / `light`, where Priming is weak)
2. **Leave work status on disk**: Write a summary to `state/current_state.md` or `shortterm/` so work can be resumed even if the session is interrupted
3. **Consult the supervisor or administrator**: If it is too tight in actual operation, consider `context_window` in `models.json` or a model change

---

## Other common problems

### File not found

- **Cause**: Incorrect path specification, file does not exist
- **Resolution**: In Mode S, use `Glob`; otherwise, use `search_memory` or `read_memory_file` on known paths
- **Note**: `read_memory_file` can read shared directories with the `common_knowledge/`, `reference/`, and `common_skills/` prefixes in addition to Anima-directory-relative paths (e.g., `knowledge/xxx.md`). For `Read` (agent built-in), paths are determined by different rules

### Cannot specify inbox with read_channel

- **Cause**: `read_channel` is for shared channels on the Board. The inbox (receive box) is not a channel
- **Resolution**: Inbox messages are processed automatically by the system. Specifying `inbox` or `inbox/` in `read_channel` will result in an error### Command times out

- **Cause**: Processing time exceeded `timeout`
- **Fix**: Increase the `timeout` parameter for Bash runtime (default: 30 seconds)
- **Note**: Set an appropriate timeout value for long-running commands

### The other party's Anima does not exist

- **Cause**: Incorrect Anima name, or that Anima has not been created yet
- **Fix**: Check with the supervisor. Refer to `reference/organization/structure.md` for the organization structure

### Frequent SEGV after rebuilding venv

- **Cause**: When major versions of ChromaDB or PyTorch are upgraded, they become incompatible with existing vectordb (HNSW segments), causing SEGV (Segmentation Fault) during reads. ChromaDB 1.5.x's Rust bindings have a known issue where they trigger SEGV instead of a Python exception for corrupted indexes (chromadb #6852, #6949, #6979)
- **Fix**: After rebuilding venv, always fully rebuild vectordb as well
  1. Shut down the server
  2. Delete `~/.animaworks/vectordb/` and each `~/.animaworks/animas/*/vectordb/` (or back them up first, then delete)
  3. Delete `~/.animaworks/index_meta.json`
  4. Start the server (it will be automatically re-indexed at startup)
- **Prevention**: When updating packages, check for version changes in chromadb, torch, and sentence-transformers; if there are changes, rebuild vectordb