# Common Problems and How to Handle Them

This is a reference summarizing common problems you may encounter during work and the steps to resolve them.
Each problem is documented in the format "Symptom → Cause → Resolution Steps."

When you're stuck, first read this documentation and follow the steps for the relevant item.
If the issue is not resolved here, refer to `troubleshooting/escalation-flowchart.md` and escalate appropriately.

---

## Messages Not Being Delivered

### Symptoms

- No reply to a message you sent
- The other party says they didn't receive your message
- You executed `send_message`, but the other party didn't respond

### Causes

1. Incorrect destination specification (Anima official name, user alias, `slack:` / `chatwork:` prefix, etc.) or a specification that doesn't match the resolution order
2. The server is down
3. The other Anima is stopped or disabled, or its Inbox is waiting for provider-error backoff
4. A real delivery error occurred during recipient resolution, permission checks, or external-channel delivery
5. `intent` is unspecified or invalid. For DMs, only `report` / `question` are allowed. For task delegation, use `delegate_task` (attaching `intent="delegation"` to `send_message` returns a deprecation message)
6. A DM was already sent to the same recipient in this run (only a second message to that recipient is rejected; there is no recipient-count cap)

### Resolution Steps

1. **Verify the recipient name and destination format**
   - Confirm that the `to` parameter in `send_message` resolves to the intended recipient
   - The resolution order in the implementation (`core/messaging/outbound.py` `resolve_recipient`) is roughly as follows:
     1. **Exact match** with a known Anima name (case-sensitive) → internal
     2. **Alias** in `config.json` `external_messaging.user_aliases` (case-insensitive) → external (preferred_channel)
     3. `slack:USERID` / `chatwork:ROOMID` → direct external
     4. Bare Slack user ID (`U` + 8 or more alphanumeric characters) → direct Slack
     5. **Case-insensitive match** with a known Anima name → internal
     6. Anything else → resolution failure
   - To reliably reach an internal Anima, use the **official name** on `~/.animaworks/animas/<名前>/` or `reference/organization/structure.md`
   - How to check:
     ```
     search_memory(query="組織", scope="common_knowledge")
     ```
     Or check all Anima names in the organization via `read_memory_file(path="reference/organization/structure.md")`
   - **Note**: In chat, `send_message` cannot be used for human recipients. Reply directly with text to reach a human. Outside chat (e.g., heartbeat), use `call_human` to contact a human

2. **Check the server status**
   - Since you are running, the server should be operational
   - If still concerned, report to your supervisor that "messages are not being delivered"

3. **Wait for the other party's response**
   - The other party checks their inbox at heartbeat intervals (e.g., every 30 minutes)
   - Even if there's no immediate reply, it will be processed at the next heartbeat
   - For urgent matters, report to your supervisor that you "need to make urgent contact" and request a manual startup

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
# One DM per recipient per run; there is no recipient-count cap
send_message(
    to="aoi",
    content="了解しました。作業を開始します。",
    intent="report",           # 必須: report / question
    reply_to="msg-abc123",     # 任意: 元メッセージのID
    thread_id="thread-xyz789"  # 任意: スレッドID
)

# Do not reply to acknowledgement/thanks/praise-only messages; use post_channel for team-wide sharing
```

---

## Unable to Proceed with a Task

There is no such state as "waiting for conditions to be met" or "blocked" (`blocked` has been deprecated). You can only choose from three options: proceed, close, or consult.

### Symptoms

- You tried to proceed with work but lack the necessary information or permissions
- You are waiting for another Anima to complete their work
- An external service returns an error

### Causes

1. A dependent task is incomplete
2. Insufficient permissions (an operation not allowed in `permissions.json`. Even in an environment with only `permissions.md`, JSON is generated on the first `load_permissions`, and the MD is moved to `.bak`)
3. Necessary information is missing
4. An external service outage

### Resolution Steps

1. **Don't repeat the same operation**
   - Identify specifically what is missing
   - Clarify "whose," "what work," and "by when" is needed

2. **Determine whether you can resolve it yourself**
   - Consider whether a different approach can work around the issue
   - Search your memory to see if a similar problem occurred in the past:
     ```
     search_memory(query="エラー内容やキーワード", scope="episodes")
     search_memory(query="回避", scope="knowledge")
     ```

3. **If you can't resolve it, report to the requester** (see `troubleshooting/escalation-flowchart.md`). Include the following in your report:
   - What you tried to do
   - What is missing or what you are waiting for
   - What you attempted yourself and your recommendation
   ```
   send_message(
       to="上司の名前",
       content="【進捗報告】\nタスク: XXXの実装\n事実: YYYのAPI権限が不足\n試行: permissions.jsonを確認したが該当設定なし\n推奨: API権限の追加をお願いします",
       intent="report"
   )
   ```

4. **Decide how to handle the task**
   - If there's a chance you'll continue, you don't need to do anything (the task remains in `pending`. Even if the session ends without a declaration, it automatically returns to `pending`)
   - If it's no longer needed, set it to `update_task(status="cancelled", summary="理由")`

5. **Check whether there's other work you can do while waiting**
   - Persistent task queue: check via `list_tasks` if the tool is available, or `Bash: animaworks-tool task list`
   - Check `list_tasks(detail=true)` for unstarted tasks, dependencies, and reasons requiring action. Do not duplicate existing tasks or manually re-submit them
   - Start working on a different task

---

## Memory Not Found

### Symptoms

- You can't recall something you did in the past
- A procedure document should exist but can't be found
- Searches return no relevant results

### Causes

1. The search keywords are not appropriate
2. The search scope is too narrow
3. It hasn't been written to memory yet (first-time work)
4. The file path is incorrect

### Resolution Steps

1. **Widen the scope and search again**
   - First, search broadly with the `all` scope:
     ```
     search_memory(query="検索したいキーワード", scope="all")
     ```
   - If there are too many results, narrow the scope:
     ```
     search_memory(query="Slack設定", scope="procedures")    # Limited to procedure documents
     search_memory(query="Slack障害", scope="episodes")      # Limited to past events
     search_memory(query="Slack", scope="knowledge")         # Limited to learned knowledge
     ```

2. **Try different keywords**
   - Try synonyms and related terms (e.g., "送信", "メッセージ", "通知", "連絡")
   - Also try English keywords (e.g., "slack", "message", "send")
   - Be aware of partial matches (e.g., "Chatwork" → "chatwork", "チャットワーク")

3. **Search shared knowledge**
   - If it's not in your personal memory, it may exist in shared knowledge:
     ```
     search_memory(query="検索キーワード", scope="common_knowledge")
     ```
   - Check the table of contents of shared knowledge:
     ```
     read_memory_file(path="common_knowledge/00_index.md")
     ```

4. **Check the directory directly**
   - In Mode S (Claude Agent SDK) and similar, the built-in `Glob` can list the contents under the Anima directory. In Mode A and similar, open a known path with `read_memory_file`, or search broadly with `search_memory`
   - If you know the file name, read it directly:
     ```
     read_memory_file(path="procedures/slack-setup.md")
     read_memory_file(path="knowledge/xxx-findings.md")
     ```

5. **If the memory doesn't exist**
   - It may be a first-time task
   - Check whether shared knowledge (`common_knowledge/`) has a relevant guide
   - Ask your supervisor or colleagues if they have any insights
   - After completing the work, record it in memory as required (for next time)
   - Old or duplicate memories can be moved to archive/ using `archive_memory_file(path="...", reason="...")` (a move, not a deletion. `reason` is required)

### Search Scope List

| scope | Search target | Use case |
|-------|---------|------|
| `knowledge` | Learned knowledge and know-how | Response policies, technical notes |
| `episodes` | Past action logs | Fact-checking "what was done when" |
| `procedures` | Procedure documents | Checking "how to do" procedures |
| `common_knowledge` | Knowledge shared by all Animas | Organization rules, system guides |
| `skills` | Skills and common skills (vector search) | Discovering and searching skills |
| `activity_log` | Recent action logs (tool execution results, messages, etc.) | Fact-checking recent items like "the email I just read" or "the search result from earlier" |
| `all` | All of the above (vector search + activity_log BM25 integrated via RRF) | Checking whether a keyword exists, broad searches |

---

## No Permission

### Symptoms

- Running a tool returned an error like "権限がありません" or "Permission denied"
- You tried to read or write a file but couldn't access it
- You tried to run a command but it was rejected

### Causes

1. An operation not allowed in `permissions.json` (if only `permissions.md` is present, `load_permissions` is normalized to JSON-equivalent on read. Invalid JSON may be warned and fall back to open defaults)
2. The external tool category is not enabled in the registry (`available_but_not_enabled` in `check_permissions`)
3. The file path is outside the allowed range (writing to protected files, outside `file_roots`, etc.). Additionally, **global** denials exist in both `permissions.global.json` and framework-side patterns

### Troubleshooting Steps

1. **Check your permissions**
   ```
   check_permissions()
   ```
   - Returned as JSON. Check `internal_tools`・`external_tools.enabled` / `available_but_not_enabled`・`file_access` (read/write）・`restrictions`（ command deny, etc.)
   - Raw configuration can be checked with `read_memory_file(path="permissions.json")` (or `permissions.md` if it does not exist)
   - The permission explanation injected into the system prompt is text formatted by the runtime from JSON

2. **Check whether the operation is allowed**
   - You can generally read and write within your own `anima_dir` (excluding protected files such as `identity.md`). Depending on your role, read access to supervisors’ and coworkers’ `activity_log` and subordinates’ `state/` is reflected in `check_permissions`’s `file_access`
   - Shell commands: `permissions.json`’s `commands` (follow allow/deny）; global dangerous patterns are also blocked by the framework)

3. **What to do when you need permission**
   - Reconsider whether the operation is truly necessary
   - Consider whether another approach (an operation within the permitted scope) could work instead
   - If there is no alternative, ask your supervisor for additional permissions:
   ```
   send_message(
       to="上司の名前",
       content="【権限追加依頼】\n目的: XXXの作業のため\n必要な権限: /path/to/dir の読み取り\n理由: YYYの情報を参照する必要があるため",
       intent="question"
   )
   ```

4. **Things you must never do**
   - Try to bypass permission checks
   - Try to execute a disallowed command by another method
   - Try to use another Anima’s permissions

---

## Tools Not Usable

### Symptoms

- You called a tool but got an error like "ツールが見つかりません"
- External tools (Slack, Gmail, etc.) are unavailable

### Cause

1. The tool is not permitted in `permissions.json` (or MD-derived configuration normalized at load time), or gated actions are not explicitly permitted
2. The skill file is not found
3. External service authentication credentials are not configured

### Resolution Steps

1. **Check how to use the tool in the skill**
   - Specify the path shown in the skill catalog of the system prompt with `read_memory_file` (e.g., `skills/foo/SKILL.md`, `common_skills/bar/SKILL.md`) and retrieve the full procedure
   - If external tools are permitted in B-mode, they can be called with `Bash: animaworks-tool <ツール> <サブコマンド>`

2. **Check permissions**
   ```
   check_permissions()
   ```
   - `external_tools.enabled`: External tool categories registered in this Anima's tool registry (those actually passed to the session)
   - `external_tools.available_but_not_enabled`: Categories implemented in the framework but not in this Anima's registry. Check together with `permissions.json` for permissions, gated actions, and execution mode

3. **If unavailable**
   - Check with `permissions.json` whether the relevant tool/action is permitted and whether authentication credentials (e.g., `shared/credentials.json`) exist
   - If still not possible, request from the supervisor (state clearly "why this tool is needed")

4. **For MCP integration mode (S/C/D/G: Claude Agent SDK / Codex CLI / Cursor Agent / Gemini CLI)**
   - Built-in tools are available without a prefix (e.g., `send_message`). If not found, a process restart is required
   - For external tools, read the skill body with `read_memory_file` to check CLI usage, and execute `animaworks-tool <ツール> <サブコマンド>` via **Bash** (using the agent's Bash tool)
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
   - For external tools, read the skill body with `read_memory_file` to check usage, and execute `animaworks-tool <ツール> <サブコマンド>` via **Bash**

8. **If the tool returns an error**
   - Record the error message accurately
   - If it is an authentication error, report to the supervisor (credential configuration is the administrator's responsibility)
   - If it is a temporary timeout or rate limit, wait briefly and retry (the number and interval depend on the tool implementation and server configuration)
   - If it does not improve, report the facts and what was tried to the requester

See `operations/tool-usage-overview.md` for the overall tool architecture.

---

## Context has become too long

### Symptoms

- The session has been running for a long time
- Responses have become slower
- A notification from the system indicates "approaching the context limit"

### Cause

- The context window has been consumed by long-running work or numerous tool calls
- Large amounts of file content were read

### Resolution Steps

1. **Save the work state to short-term memory** (MUST)
   - Write the current work state to `shortterm/` (or `shortterm/chat/` during chat sessions):
   ```
   write_memory_file(
       path="shortterm/chat/session_state.md",
       content="## 作業状態\n\n### 実行中のタスク\n- XXXの実装（50%完了）\n\n### 次のステップ\n1. YYYを完了する\n2. ZZZをテストする\n\n### 重要な中間結果\n- AAAの調査結果: BBB\n- CCCの設定値: DDD",
       mode="overwrite"
   )
   ```
   - Use `shortterm/heartbeat/session_state.md` during heartbeat sessions

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

- For large files, do not read the entire file; search only the necessary parts
- For long tasks, update `state/current_state.md` regularly
- Write intermediate results to memory frequently

---

## A message send returned an error

### Symptoms and causes

- A real delivery error is returned, such as `RecipientResolutionError`, external-channel `DeliveryFailed`, a permission error, or a company-boundary error
- A second `send_message` to the same recipient in one run is rejected to prevent duplicates. There is no recipient-count cap
- A second `post_channel` to the same channel in one run is rejected. There is no cross-run posting cooldown
- There are no hourly/daily send budgets or conversation-depth send blocks. Depth between internal Animas may be recorded for diagnostics

### Resolution steps

1. **Inspect the error**: Check recipient resolution, `intent` (`report` / `question`), channel ACL, company boundaries, or the external API response
2. **Check for duplicates**: A recipient already messaged in this run cannot receive another DM in that run. There is no need to wait for a recipient-count limit
3. **Investigate delivery failures**: For Slack / Chatwork, check the returned delivery error and connection settings
4. **For Inbox provider errors**: Unread messages are retried after the recovery time specified by `rate_guard`

See `communication/sending-limits.md` for details.

---

## Command was blocked

### Symptoms

- An error such as "PermissionDenied" or "Command blocked" was returned when trying to execute a command
- Only specific commands cannot be executed

### Cause

1. Commands matching the global deny patterns of the framework or `permissions.global.json` (e.g., `rm -rf /`, etc.)
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
   - Request the supervisor to unblock
   - When requesting, clearly state "why this command is needed"

---

## Prompt was shortened

### Symptoms

- The system prompt is thinner than usual, and Priming (automatic recall) is nearly empty
- After long conversations or large user messages, there is behavior as if the prompt was rebuilt before responding

### Causes

There are two main layers.

**1. Priming (automatic recall) tiers** — `resolve_prompt_tier(context_window)` in `core/prompt/builder.py` determines the tier based on the estimated context window. The window resolution order is `core/prompt/context.py` `resolve_context_window`: **`~/.animaworks/models.json` (SSoT)** → deprecated `config.json` `model_context_windows` → in-code fallbacks such as `MODEL_CONTEXT_WINDOWS` → default 128k.

| Tier | Condition (`context_window`) | Priming behavior (`core/agent/priming.py`) |
|--------|--------------------------|---------------------------------------------|
| full | **≥ 128_000** | Format and include normal compact retrieval within the bounds of `priming.max_tokens` |
| standard | **≥ 32_000 and < 128_000** | Same compact path, but limit the retrieval budget to a maximum of 1000 tokens |
| light | **≥ 16_000 and < 32_000** | Retrieve the basic compact context and suppress related knowledge and episode searches |
| minimal | **< 16_000** | Retain the basic compact context and suppress related knowledge and episode searches |

Heartbeat/cron query text consists of text collected from recent `[REFLECTION]` in activity_log (not the full, lengthy template).

**2. Shrinking the system prompt itself** — `core/agent/priming.py` `_fit_prompt_to_context_window`: when the estimated tokens for system + user messages, plus tool schema overhead, exceed **about 80% of the context window**, rebuild by progressively shrinking `build_system_prompt`’s system budget from **75% → 50% → 25%**. At the **25% or lower tier**, empty the **Priming block and human-facing notification block** before applying it. If it still doesn’t fit, **hard-truncate the system prompt byte by byte**.

### Resolution Steps

1. **Explicitly retrieve missing context**: Read organization, procedures, and shared knowledge with `search_memory` / `read_memory_file` (especially in `minimal` / `light` where Priming is weak)
2. **Leave work state on disk**: Write a summary to `state/current_state.md` or `shortterm/` so work can be resumed even if the session is interrupted
3. **Consult the supervisor or administrator**: If it is too tight in actual operation, consider `context_window` of `models.json` or a model change

---

## Other common problems

### File not found

- **Cause**: Incorrect path specification, file does not exist
- **Resolution**: In Mode S, use `Glob`; otherwise, use `search_memory` or `read_memory_file` on known paths
- **Note**: `read_memory_file` can read shared directories with `common_knowledge/`, `reference/`, and `common_skills/` prefixes in addition to Anima-directory-relative paths (e.g., `knowledge/xxx.md`). For `Read` (agent built-in), paths are determined by different rules

### read_channel cannot specify inbox

- **Cause**: `read_channel` is for shared channels on the Board. Inbox is not a channel
- **Resolution**: Inbox messages are processed automatically by the system. Specifying `inbox` or `inbox/` in `read_channel` will result in an error

### Command times out

- **Cause**: Processing time exceeded `timeout`
- **Fix**: Increase the `timeout` parameter for Bash runtime (default: 30 seconds)
- **Note**: Set an appropriate timeout value for long-running commands

### The other party's Anima does not exist

- **Cause**: Incorrect Anima name, or that Anima has not been created yet
- **Fix**: Check with your supervisor. Refer to `reference/organization/structure.md` for the organization structure

### Frequent SEGV after rebuilding venv

- **Cause**: When major versions of ChromaDB or PyTorch are upgraded, they become incompatible with existing vectordb (HNSW segments), causing SEGV (Segmentation Fault) during reads. ChromaDB 1.5.x's Rust bindings have a known issue where they trigger SEGV instead of a Python exception for corrupted indexes (chromadb #6852, #6949, #6979)
- **Fix**: After rebuilding venv, always fully rebuild vectordb as well
  1. Shut down the server
  2. Delete `~/.animaworks/vectordb/` and each `~/.animaworks/animas/*/vectordb/` (or back them up first, then delete)
  3. Delete `~/.animaworks/index_meta.json`
  4. Start the server (it will be automatically re-indexed at startup)
- **Prevention**: When updating packages, check for version changes in chromadb, torch, and sentence-transformers; if there are changes, rebuild vectordb
