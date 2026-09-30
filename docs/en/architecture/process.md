<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/architecture/process.md -->
<!-- i18n: source-sha256=c13b2a6ee7d7489c293fb54000a394e0170b3a4c9fac8f7cc3ddbee4cc825829 generated=2026-09-30 engine=local model=deepseek-v4-flash translator=2 -->

> Confirmed commit: b304b7dc

# Process Structure and Communication

The runtime assumes the phase3 process structure. The server provides API and WebSocket, and the Process Supervisor within the same server manages the Anima root process. The root has a scheduler and control IPC, and passes conversations and background processing to a separate task runner.

```mermaid
flowchart LR
    Server[server / Process Supervisor] -->|起動・監視| Root[Anima root]
    Server <-->|制御 IPC| Root
    Root -->|IPC v2 の要求| Runner[task runner]
    Runner -->|進捗・結果| Root
    Runner -->|HTTP の記憶 URL| Memory[記憶サービス]
```

## Startup and IPC

`core/supervisor/manager.py` starts the root process, and `core/supervisor/runner.py` initializes Anima's runtime objects and each service. `core/supervisor/task_runner_supervisor.py` starts an independent task runner for each request, executing heartbeat, cron, inbox, chat, greet, background tasks, and more in isolation.

Control communication between the root and server goes through `core/supervisor/ipc.py`. `core/supervisor/ipc_v2.py` handles requests and responses between the root and task runner, and `core/supervisor/transport.py` selects the connection method. Unix domain sockets are used by default, with loopback TCP on Windows. If the Unix socket path exceeds the OS length limit, it also switches to loopback TCP.

The connection target needed for vector search is prepared as a URL by the server at startup and passed to the task runner. The root manages access to memory data, and child processes search via the service. See `docs/ja/memory/retrieval.md` for details on the search path.

## Startup Preparation and Readiness

The server does not make all APIs available immediately after startup; it proceeds with RAG preflight and Anima process startup. During preparation, startup progress is updated, and the readiness gate returns a progress screen. The Anima root continues initialization even after creating the IPC endpoint, and receives supervisor confirmation after ping returns ready. Public readiness does not become ready until heavy startup preparation and dependency service initialization are complete.

## Abnormal Termination and Restart

The state machine in `core/supervisor/restart_state.py` centrally manages the consecutive failure count, next restart time, and last error for each Anima. After a specified number of failures, FAILED is displayed in the UI, but automatic recovery continues. The restart interval is extended with exponential backoff, with a maximum of 30 minutes. The failure count is reset after stable operation continues.

The engine's idle timeout applies when no engine event arrives for 1200 seconds. This is not a limit on the total execution time of a conversation. The task runner's shutdown and response monitoring is handled by the supervisor on the root side.
