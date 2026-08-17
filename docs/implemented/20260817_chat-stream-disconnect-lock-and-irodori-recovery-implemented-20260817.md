# Chat stream切断時の固着解消とIrodori復旧 — close伝播を保証し既存systemd運用を正常化する

## Overview

meiのchat IPC接続が応答途中で切断された際、入れ子のasync generatorが閉じられず、`TaskRunnerSupervisor._chat_lock`が永続的に保持された。IPC境界のclose伝播を決定的にし、併発しているIrodori-TTSの壊れた仮想環境を再構築して、既存のsystemd自動再起動へ戻す。

## Problem / Background

### Current State

- 2026-08-17 21:34:36、meiのchat streamで`ConnectionResetError`と`BrokenPipeError`が発生した。
- 子chat processは21:37:53に完了したが、async generator finalizerで`ContextVar ... created in a different Context`が発生した。
- 以降のchatは子processを起動できず、300秒のIPC timeoutになった。runner自体のping、running-task API、active-stream APIは正常表示のままだった。
- `core/supervisor/ipc.py:202`はstreaming iteratorを裸の`async for`で消費する。
- `core/supervisor/streaming_handler.py:102`もisolated chat streamを裸の`async for`で消費する。
- `core/supervisor/task_runner_supervisor.py:282`はgeneratorの生存中、`_chat_lock`を保持する。
- Irodoriのuser serviceは有効かつ`Restart=always`だが、約10秒ごとにexit status 2で再起動している。
- `/home/main/vendor/Irodori-TTS/.venv/pyvenv.cfg`は再起動で消えた`/tmp/irodori-uv-python/...`を参照し、再構築は`.venv`内2,925件のroot所有物に阻害されている。

### Root Cause

1. IPC write失敗時に`handler_result.aclose()`が呼ばれず、外側generatorのcleanupがGCへ先送りされる — `core/supervisor/ipc.py:199`。
2. 外側を閉じてもisolated chatの内側generatorへcloseが伝播せず、producer cancelとchat lock解放が実行されない — `core/supervisor/streaming_handler.py:102`、`core/supervisor/task_runner_supervisor.py:307`。
3. Irodoriのvenvが一時領域のPythonに結びついており、再起動後のuv再構築にroot所有物が残った — `/home/main/vendor/Irodori-TTS/.venv/pyvenv.cfg:1`。

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| Chat IPC | Direct | 1回のクライアント切断で対象Animaのchat laneが再起動まで固着する |
| Voice chat | Direct | 同じchat laneを使うため無応答になる |
| Task runner | Direct | 完了済みまたは不要なproducerのcleanupが走らない |
| Irodori-TTS | Direct | port 7861がlistenせず、音声合成できない |
| Status API | Indirect | runner aliveのため障害が表面化しにくい |

## Decided Approach / 確定方針

### Design Decision

確定: streaming iteratorを所有する2つの境界で、同じtask/context内から明示的に`aclose()`する。IPCServerは任意の`AsyncIterator`を受けるため`aclose`の有無を確認してfinallyでawaitし、StreamingIPCHandlerは自身が生成する`run_chat_stream()`を`contextlib.aclosing()`で囲む。Irodoriは新規監視コードを追加せず、壊れたvenvの所有権を修復して`uv sync --frozen --extra cu128`で永続uv Pythonに再構築し、既存のenabled user serviceと`Restart=always`を利用する。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| chat lockへタイムアウトを追加 | 表面的には再開できる | 実行中producerを残し、二重実行や応答混線を起こす | **Rejected**: cleanup漏れを温存する |
| mei固有の再起動・例外処理 | 変更が局所的 | 全Animaとvoiceの共通IPC経路で再発する | **Rejected**: 共通原因を直さない |
| TaskRunnerSupervisorのlock処理を変更 | lock箇所で対処できる | generatorが閉じられない限りfinallyへ到達しない | **Rejected**: 所有者側のclose漏れが原因 |
| Irodori watchdogを新設 | 監視を追加できる | systemdが既に同機能を持ち、現在も再起動を試行している | **Rejected**: venv破損を直さず複雑性だけ増やす |
| **所有境界でclose + venv再構築** | 根因を共通箇所で解消する | 2段それぞれのcloseが必要 | **Adopted**: 最小差分でロック、子process、ContextVarを一括cleanupできる |

### Key Decisions from Discussion

1. **closeはIPCとnested streamの両境界で保証する** — 片方だけでは内側generatorが生存した。
2. **TaskRunnerSupervisor本体は変更しない** — generatorが閉じられれば既存finallyがproducer cancel・回収・lock解放を正しく行う。
3. **Irodoriのservice定義は変更しない** — `enabled`、linger、`Restart=always`が既に自動復帰要件を満たす。
4. **本番適用はmain統合後にmeiを再起動する** — 現在保持されているin-memory lockを解消し、修正版をロードする。

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/supervisor/ipc.py` | Modify | streaming handler resultをfinallyで明示的にcloseする |
| `core/supervisor/streaming_handler.py` | Modify | isolated chatのnested iteratorを`aclosing()`で閉じる |
| `tests/unit/test_ipc_dedicated_stream.py` | Modify | write切断時に入れ子stream cleanupまで到達する回帰テストを追加する |
| `core/supervisor/task_runner_supervisor.py` | No change | 既存finallyはclose後に正しくlockとproducerをcleanupする |
| `~/.config/systemd/user/irodori-tts.service` | No change | 既存の自動再起動設定を継続使用する |

### Edge Cases

| Case | Handling |
|------|----------|
| 正常なstream完走 | closeは冪等な終了処理となり、最終responseを変えない |
| write中の`BrokenPipeError`/`ConnectionResetError` | error応答の再送に失敗してもfinallyでstreamを閉じる |
| task cancellation/`GeneratorExit` | `BaseException`を握り潰さず、context managerの終了処理後に伝播させる |
| `aclose`を持たない独自AsyncIterator | IPC層はclose methodの有無を確認し、通常反復だけを行う |
| nested producerが実行中 | `run_chat_stream()`既存finallyがcancelし、`gather(..., return_exceptions=True)`で回収する |
| Irodori起動時のGPU preload | `/health`成功まで待機し、起動途中を成功扱いしない |
| Irodori再失敗 | systemd status、journal、安定した`NRestarts`で検出する |

## Implementation Plan

### Phase 1: Stream cleanup

| # | Task | Target |
|---|------|--------|
| 1-1 | IPC streaming resultをfinallyでcloseする | `core/supervisor/ipc.py` |
| 1-2 | isolated chat nested streamを`aclosing()`で囲む | `core/supervisor/streaming_handler.py` |

**Completion condition**: write失敗時にも`run_chat_stream()`のfinallyへ到達する。

### Phase 2: Regression verification

| # | Task | Target |
|---|------|--------|
| 2-1 | 切断を模したwriterでstream closeを検証する | `tests/unit/test_ipc_dedicated_stream.py` |
| 2-2 | supervisor/IPC関連テストとruffを実行する | test/lint commands |

**Completion condition**: producerがcancel・回収され、chat lockが解除され、既存テストも成功する。

### Phase 3: Deployment and recovery

| # | Task | Target |
|---|------|--------|
| 3-1 | mainへレビュー済み変更を統合する | repository main |
| 3-2 | mei runnerを再起動し修正版をロードする | runtime mei |
| 3-3 | Irodori serviceを停止し、sudo gate経由でvenv所有権を修復する | `/home/main/vendor/Irodori-TTS/.venv` |
| 3-4 | frozen cu128環境を再構築してserviceを開始する | Irodori user service |
| 3-5 | mei状態、Irodori health、restart counterを検証する | runtime APIs/systemd |

**Completion condition**: meiが新PIDでhealthy、Irodoriがactiveかつ`/health`成功、restart counterが安定する。

## Scope

### In Scope

- IPC切断時の外側・内側async generator cleanup
- chat lockとproducerの決定的解放
- 最小の回帰テスト
- main統合とmei再起動
- Irodori venv修復と既存systemd自動復帰の動作確認

### Out of Scope

- chat lockのタイムアウト化 — cleanup後は不要
- status APIへのlock状態追加 — 今回の根因修正に不要
- Irodori watchdog、Docker化、AnimaWorksとのunit結合 — systemd単体で自動復帰済み
- Irodori vendorソースの変更 — 実行環境破損のみが原因
- 実音声の合成送信 — `/health`でサービス復旧を検証し、外部送信を避ける

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| close時に既存の例外を上書きする | 障害原因が不明瞭になる | cleanupをfinallyで行い、切断時も元の制御フローを維持する |
| nested producer cancelで途中応答が失われる | 切断したrequestの応答は完了しない | クライアント切断済みのrequestだけを対象とし、次requestの健全性を優先する |
| venv再構築が長時間・大容量になる | Irodori停止時間が延びる | serviceを先に停止し、lockfile固定の`--frozen --extra cu128`を使う |
| GPU preload中を失敗と誤判定する | 不要な再操作 | service activeと`/health`成功まで待つ |
| dirty mainの既存変更と衝突する | ユーザー変更を損なう | 専用worktreeで実装し、対象ファイルだけ統合する |

## Acceptance Criteria

- [ ] IPC writerが最初のstream responseで失敗しても、handler resultが明示的にcloseされる。
- [ ] nested isolated chat streamのproducerがcancel・回収される。
- [ ] 切断処理後に`TaskRunnerSupervisor._chat_lock.locked()`がfalseになる。
- [ ] 正常streamと非stream IPCの既存挙動が変わらない。
- [ ] 対象unit testsとruffが成功する。
- [ ] main統合後、meiが新PIDでrunningかつpingに応答する。
- [ ] Irodori serviceが`active`、`http://127.0.0.1:7861/health`が成功する。
- [ ] Irodoriの`NRestarts`がhealth確認期間中に増加しない。

## References

- `core/supervisor/ipc.py:178` — IPC connection lifecycle
- `core/supervisor/streaming_handler.py:80` — outer streaming generator
- `core/supervisor/task_runner_supervisor.py:266` — isolated chat stream and lock ownership
- `core/supervisor/runner.py:774` — streaming handlerをIPCへ返す箇所
- `tests/unit/test_ipc_dedicated_stream.py:64` — dedicated stream IPC tests
- `/home/main/.config/systemd/user/irodori-tts.service:6` — Irodori working directory and restart policy
- [Python 3.12 contextlib.aclosing](https://docs.python.org/3.12/library/contextlib.html#contextlib.aclosing) — same-context async generator cleanup
- [Python async for semantics](https://docs.python.org/3.12/reference/compound_stmts.html#the-async-for-statement) — iterator close is implicitでないこと
