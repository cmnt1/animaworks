# Windows-native Codex fork plan

## Goal

Run AnimaWorks on native Windows without WSL and allow Mode C to use an
interactive Codex login instead of requiring `OPENAI_API_KEY`.

## Scope for phase 1

- Native Windows server start/stop
- Native Windows child-process supervision
- Native Windows IPC for Anima runners
- Mode C only for subscription-backed Codex auth
- No attempt to make every shell-oriented tool behave identically on day one

## Why this order

Do not start with auth or UI work. The highest-risk area is the Unix process
model. If that remains unstable, auth debugging becomes noise.

Recommended order:

1. Stabilize platform seams
2. Replace Unix-only IPC and locking
3. Make process lifecycle work on Windows
4. Enable Codex subscription auth for Mode C
5. Restore secondary features and packaging

## Current blockers by subsystem

### 1. IPC transport

Current implementation is hard-coded to Unix domain sockets.

Primary files:

- `core/supervisor/ipc.py`
- `core/supervisor/process_handle.py`
- `core/supervisor/manager.py`
- `tests/unit/test_ipc_chunk.py`
- `tests/unit/test_ipc_dedicated_stream.py`

Current assumptions:

- `asyncio.start_unix_server`
- `asyncio.open_unix_connection`
- `*.sock` paths under `run/sockets`

Phase 1 recommendation:

- Introduce a transport abstraction with one request/response protocol
- Keep the JSONL wire format unchanged
- Add two implementations:
  - `UnixSocketTransport`
  - `TcpLoopbackTransport` for Windows

Named pipes are a stronger long-term Windows fit, but localhost TCP is the
shortest path to a working fork. If TCP is used, add a per-process random
auth token so other local processes cannot attach trivially.

### 2. File locking

Current implementation uses `fcntl.flock`.

Primary files:

- `core/supervisor/runner.py`
- `core/notification/reply_routing.py`

Phase 1 recommendation:

- Add a small lock adapter module
- Use `fcntl` on POSIX
- Use a cross-platform library such as `portalocker` on Windows

### 3. Process lifecycle

Current implementation assumes POSIX sessions, `/proc`, and signals.

Primary files:

- `cli/commands/server.py`
- `core/supervisor/process_handle.py`
- `core/supervisor/manager.py`
- `core/tooling/handler_files.py`
- `core/tools/machine.py`

Current assumptions:

- `start_new_session=True`
- `os.killpg`
- `/proc` scanning
- `os.getuid`
- `SIGTERM` / `SIGKILL` workflow

Phase 1 recommendation:

- Replace `/proc` scans with `psutil`
- Replace process-group killing with a platform adapter
- On Windows, use `CREATE_NEW_PROCESS_GROUP` plus terminate/kill fallbacks
- Treat orphan cleanup as best-effort instead of `/proc`-driven certainty

### 4. Shell execution

Several features assume Bash behavior.

Primary files:

- `core/tooling/handler_files.py`
- `core/_anima_lifecycle.py`
- templates and documentation that emit `bash` commands

Phase 1 recommendation:

- Introduce a shell adapter:
  - POSIX: existing behavior
  - Windows: `pwsh -NoProfile -Command`
- Keep raw command execution available, but mark Bash-specific workflows as
  unsupported until explicitly ported

### 5. Codex auth

Mode C already contains the right architectural hook: per-anima `CODEX_HOME`
plus propagation of the shared `~/.codex/auth.json`.

Primary files:

- `core/execution/codex_sdk.py`
- `README.md`

Completed in this branch:

- `CODEX_HOME` env now uses a platform-safe `HOME` fallback
- PATH fallback is no longer POSIX-only
- `auth.json` propagation now falls back from symlink -> hardlink -> copy

Remaining work:

- Update setup and UI copy so Mode C does not imply API-key-only auth
- Detect "logged into Codex but no API key" as a valid setup state
- Add explicit diagnostics when Mode C fails because no Codex auth is present

## Phased execution plan

### Phase 0: Audit and safety rails

- Freeze an upstream base commit
- Add a Windows CI job with allowed failures
- Add a migration checklist document

Exit criteria:

- All known platform-specific files are catalogued

### Phase 1: Transport and locking

- Add IPC transport abstraction
- Land Windows transport implementation
- Replace direct `fcntl` usage with a lock adapter

Exit criteria:

- One Anima process can start, accept a `ping`, and stop on Windows

### Phase 2: Supervisor and process controls

- Replace `/proc` and signal-only logic
- Port orphan detection and shutdown flow
- Make background command handling degrade cleanly on Windows

Exit criteria:

- Server can start, restart, and stop reliably on Windows

### Phase 3: Mode C vertical slice

- Validate native Windows Codex CLI execution path
- Accept subscription login without `OPENAI_API_KEY`
- Improve failure messages for missing Codex auth

Exit criteria:

- A Windows user can run one Mode C Anima with Codex login only

### Phase 4: Secondary features

- Revisit Bash-centric task execution
- Review Slack reply routing and other file-lock users
- Port docs, setup flows, and packaging

Exit criteria:

- Windows usage is documented and repeatable

## Suggested first implementation tickets

1. Add `core/supervisor/transport.py` with a transport interface
2. Refactor `ipc.py` into protocol + transport-specific server/client pieces
3. Add `core/platform/locks.py`
4. Add `core/platform/process.py`
5. Replace `/proc` scans with `psutil`
6. Add Windows-targeted tests for supervisor startup/shutdown
7. Update setup wizard copy for Codex login

## Acceptance criteria for a practical fork

- `animaworks start` works on Windows without WSL
- A child Anima can be spawned and supervised
- Mode C works with a prior `codex login`
- Missing Codex auth produces a clear actionable error
- Existing Linux behavior remains unchanged
