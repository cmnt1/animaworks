# Agent SDK Close Patch SDK Drift — Prevent stream retries caused by stale private-attribute monkey patch

## Overview

Sakura is running with `claude-agent-sdk 0.1.81` from the ambient Python user-site while the repository lock still contains `0.1.44`. AnimaWorks applies an older monkey patch to `SubprocessCLITransport.close()` on import; that patch assumes the old SDK private attribute `_stderr_task_group`, which no longer exists in `0.1.81`. This issue makes the patch feature-detected and compatibility-safe so Mode S Agent SDK streams do not fail during teardown.

## Problem / Background

### Current State

- Sakura logs repeated `Agent SDK streaming error` entries, followed by `Stream retry exhausted (3/3)`.
- The direct exception is:

```text
AttributeError: 'SubprocessCLITransport' object has no attribute '_stderr_task_group'
```

- The stack path is `ClaudeSDKClient.__aexit__` → `disconnect()` → `Query.close()` → `transport.close()` → AnimaWorks patched close.
- `core/execution/agent_sdk.py:46` imports `apply_sdk_transport_patch()`.
- `core/execution/agent_sdk.py:48` applies the patch at module import time.
- `core/execution/_sdk_patch.py:53` directly reads `self._stderr_task_group`.
- `core/execution/_sdk_patch.py:94` globally replaces `SubprocessCLITransport.close`.
- Runtime `claude-agent-sdk 0.1.81` defines `_stderr_task` instead of `_stderr_task_group`.
- `pyproject.toml:24` allows any non-Windows `claude-agent-sdk>=0.1.40`.
- `uv.lock:827` pins `claude-agent-sdk 0.1.44`, but the live `/usr/bin/python3` runtime is not using that lock.

### Root Cause

1. **Brittle private SDK coupling** — `_sdk_patch.py` replaces an internal SDK method and assumes private attribute `_stderr_task_group` exists: `core/execution/_sdk_patch.py:53`.
2. **Unconditional patching** — `apply_sdk_transport_patch()` patches `SubprocessCLITransport.close()` regardless of SDK version or native behavior: `core/execution/_sdk_patch.py:153`.
3. **Runtime dependency drift** — repository lock has SDK `0.1.44`, but Sakura runs with user-site SDK `0.1.81`; the private transport layout changed from `_stderr_task_group` to `_stderr_task`.
4. **Retry masks deterministic local failure** — `AgentSDKExecutor.execute_streaming()` wraps teardown exceptions as `StreamDisconnectedError`: `core/execution/agent_sdk.py:701`; the retry loop then retries the same deterministic local close failure until exhaustion: `core/_agent_cycle.py:1063`.

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/execution/_sdk_patch.py` | Direct | Old close patch crashes under current SDK private layout. |
| `core/execution/agent_sdk.py` | Direct | Streaming sessions are marked disconnected during `ClaudeSDKClient` teardown. |
| `core/_agent_cycle.py` | Indirect | Retries are consumed on a deterministic local compatibility error. |
| Sakura Mode C / Mode S runtime | Direct | Inbox/message cycles can produce empty responses and leave messages unarchived. |

## Decided Approach / 確定方針

### Design Decision

確定: `core/execution/_sdk_patch.py` を SDK feature detection 方式に変更する。`SubprocessCLITransport.close()` がすでに stdin EOF 後の graceful wait を持つ場合は close patch を適用しない。古いSDKのように graceful wait がない場合のみ legacy close patch を適用し、そのlegacy patchは `_stderr_task_group` と `_stderr_task` の両方を `getattr()` で扱い、private属性欠落で落ちないようにする。Windows用 `Query.wait_for_result_and_end_input()` patch も method 存在確認を行い、未対応SDKでは警告ログを出してskipする。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Pin runtime back to SDK `0.1.44` | Repo lockと一致し、旧patch前提に戻る | ambient runtimeやauto-updateで再発する。private属性依存を残す | **Rejected**: 根本原因を残すため |
| Only replace `self._stderr_task_group` with `getattr()` | 最小差分でAttributeErrorは止まる | SDK `0.1.81` のnative closeが持つ `_ACTIVE_CHILDREN` cleanupやkill fallbackを上書きし続ける | **Rejected**: 新SDKの正しいnative実装を壊すため |
| Change stream retry count/classification only | Retry浪費は減る | `transport.close()` 自体が壊れたまま | **Rejected**: primary bugの修正にならないため |
| **Feature-detected patching (Adopted)** | old SDKには必要なpatchを残し、新SDKにはnative closeを使わせる | feature detection用の小さな検査ロジックが増える | **Adopted**: SDK private layout driftに強く、既存の古いSDK対策も維持できるため |

### Key Decisions from Discussion

1. **Native graceful close existsならpatchしない**: SDK `0.1.81` の `SubprocessCLITransport.close()` はすでに5秒graceful waitを持つ — Reason: AnimaWorks patchの目的がupstream実装済みなら上書きしない方が安全。
2. **Legacy patchは両attribute形状を扱う**: `_stderr_task_group` と `_stderr_task` を `getattr()` で検出して処理する — Reason: private SDK internalsのminor release差分で落ちないようにする。
3. **Windows stdin lifecycle patchはmethod existence gatedにする**: `Query.wait_for_result_and_end_input` がないSDKではskip + warningにする — Reason: SDK `0.1.44` にはそのmethod boundaryがなく、存在しないmethodを前提にすると別のImport時障害になる。
4. **Retry behaviorは今回変更しない**: close patch compatibilityを直せば今回のdeterministic retry exhaustionは消える — Reason: retry policy変更は別設計で、今回のprimary bug修正には不要。

### Changes by Module

| Module | Change Type | Description |
|--------|-------------|-------------|
| `core/execution/_sdk_patch.py` | Modify | `SubprocessCLITransport.close` のfeature detectionを追加。native graceful closeならskipし、legacy patchはprivate attribute欠落に耐える。Windows Query patchもmethod existence checkを追加。 |
| `tests/unit/execution/test_sdk_patch.py` | New | close patch gating、old/new stderr task形状、attribute欠落、Windows method absenceの単体テストを追加。 |
| `core/execution/agent_sdk.py` | No change | import時に `apply_sdk_transport_patch()` を呼ぶ既存経路は維持する。 |
| `core/_agent_cycle.py` | No change | retry exhaustionはsecondary symptomなので今回の実装修正対象外。 |

#### Change 1: Feature-detect native graceful close

**Target**: `core/execution/_sdk_patch.py`

```python
# Before
SubprocessCLITransport.close = _patched_close

# After
if _native_close_has_graceful_wait(SubprocessCLITransport.close):
    logger.info("Skipping SubprocessCLITransport.close patch; SDK close is already graceful")
    return

SubprocessCLITransport.close = _patched_close
```

`_native_close_has_graceful_wait()` は `inspect.getsource()` が取得できる場合に、native close sourceが `anyio.fail_after` / `await self._process.wait()` / `terminate()` のgraceful wait patternを含むか判定する。source取得に失敗した場合は `False` としてlegacy patchを適用し、legacy patch側のcompatibility guardsで安全性を担保する。

#### Change 2: Legacy patch supports old and new stderr task layouts

**Target**: `core/execution/_sdk_patch.py`

```python
# Before
if self._stderr_task_group:
    self._stderr_task_group.cancel_scope.cancel()
    await self._stderr_task_group.__aexit__(None, None, None)
    self._stderr_task_group = None

# After
stderr_task_group = getattr(self, "_stderr_task_group", None)
if stderr_task_group:
    stderr_task_group.cancel_scope.cancel()
    await stderr_task_group.__aexit__(None, None, None)
    self._stderr_task_group = None

stderr_task = getattr(self, "_stderr_task", None)
if stderr_task is not None and not stderr_task.done():
    stderr_task.cancel()
    await stderr_task.wait()
    self._stderr_task = None
```

The implementation must guard all private SDK attributes accessed by the patch with `getattr()` or `hasattr()` where absence is possible.

### Edge Cases

| Case | Handling |
|------|----------|
| SDK `0.1.81` native close already graceful | Do not patch `SubprocessCLITransport.close`; preserve upstream `_stderr_task`, `_ACTIVE_CHILDREN`, terminate, and kill fallback behavior. |
| SDK `0.1.44` native close terminates immediately | Apply legacy graceful close patch. |
| Patched transport has no `_stderr_task_group` | No AttributeError; skip old task-group cleanup. |
| Patched transport has `_stderr_task` | Cancel and wait the task if active, then set `_stderr_task = None`. |
| Patched transport has neither stderr task attribute | No AttributeError; continue stdin/stderr/process cleanup. |
| `inspect.getsource()` fails for SDK close | Treat native close as not proven graceful; apply guarded legacy patch. |
| SDK process does not exit after stdin EOF | Wait `_GRACEFUL_EXIT_TIMEOUT_SEC`, then terminate; preserve existing legacy behavior. |
| SDK process ignores SIGTERM | In legacy patch, add a second bounded wait and `kill()` fallback only if the process exposes `kill`; mirror current SDK `0.1.81` behavior. |
| `Query.wait_for_result_and_end_input` absent on Windows | Log warning and skip Windows stdin lifecycle patch; do not fail import. |

## Implementation Plan

### Phase 1: Patch gating and compatibility

| # | Task | Target |
|---|------|--------|
| 1-1 | Add `_native_close_has_graceful_wait(close_fn)` using `inspect.getsource()` with exception-safe fallback. | `core/execution/_sdk_patch.py` |
| 1-2 | Change `_patch_transport_close()` to skip close patch when native graceful close is detected. | `core/execution/_sdk_patch.py` |
| 1-3 | Update legacy `_patched_close()` to use `getattr()` for `_process`, `_stderr_task_group`, `_stderr_task`, `_stdin_stream`, `_stderr_stream`, `_write_lock`, and optional `kill()`. | `core/execution/_sdk_patch.py` |
| 1-4 | Preserve `_GRACEFUL_EXIT_TIMEOUT_SEC` and existing import-time patch application contract. | `core/execution/_sdk_patch.py` |

**Completion condition**: Importing `core.execution.agent_sdk` under SDK `0.1.81` no longer replaces native graceful close and does not create `_stderr_task_group` AttributeErrors.

### Phase 2: Windows patch guard

| # | Task | Target |
|---|------|--------|
| 2-1 | In `_patch_query_stdin_lifecycle()`, check `hasattr(Query, "wait_for_result_and_end_input")`. | `core/execution/_sdk_patch.py` |
| 2-2 | If absent, log a warning and return without raising. | `core/execution/_sdk_patch.py` |
| 2-3 | Keep current patched no-op behavior unchanged when the method exists. | `core/execution/_sdk_patch.py` |

**Completion condition**: Windows patch path cannot fail import because an SDK version lacks `Query.wait_for_result_and_end_input`.

### Phase 3: Regression tests

| # | Task | Target |
|---|------|--------|
| 3-1 | Add unit test proving native graceful close is not overwritten. | `tests/unit/execution/test_sdk_patch.py` |
| 3-2 | Add unit test proving legacy patched close works without `_stderr_task_group`. | `tests/unit/execution/test_sdk_patch.py` |
| 3-3 | Add unit test proving legacy patched close cancels `_stderr_task_group` when present. | `tests/unit/execution/test_sdk_patch.py` |
| 3-4 | Add unit test proving legacy patched close cancels `_stderr_task` when present. | `tests/unit/execution/test_sdk_patch.py` |
| 3-5 | Add unit test proving Windows Query patch skips cleanly when the method is absent. | `tests/unit/execution/test_sdk_patch.py` |

**Completion condition**: New SDK patch tests pass under the current runtime and existing Agent SDK tests remain green.

## Scope

### In Scope

- Fix `core/execution/_sdk_patch.py` so SDK private attribute drift cannot crash `transport.close()`.
- Preserve legacy graceful close behavior for older SDK versions that still need it.
- Skip close patch for SDK versions where upstream close already implements graceful wait.
- Add focused tests for both old and new SDK private-layout shapes.

### Out of Scope

- Changing stream retry policy in `core/_agent_cycle.py` — Reason: Retry exhaustion is secondary to the broken close patch.
- Forcing all deployments to use `.venv` / `uv.lock` SDK `0.1.44` — Reason: Runtime environments can drift; code must be robust.
- Updating `uv.lock` to `0.1.81` — Reason: Dependency upgrade is separate and may affect bundled CLI/platform wheels.
- Fixing Neo4j `deleted_at` / `expired_at` warnings — Reason: Separate memory schema/log-noise issue.
- Fixing `ContextVar token created in a different Context` log seen later in Sakura logs — Reason: Separate async generator context cleanup issue.

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Native close detection false negative | New SDK still gets legacy patch | Guard legacy patch with `getattr()` for both private layouts and preserve kill fallback. |
| Native close detection false positive | Old SDK may keep immediate terminate behavior | Detection must require graceful wait markers, not only `terminate()`. Unit-test old-style close source. |
| Monkey patch tests mutate global SDK class | Later tests may see patched close | Use isolated fake transport classes for helper tests; when real class is patched, restore original close in test teardown. |
| Windows patch skipped on older SDK | Windows stdin freeze mitigation may not apply to that exact SDK | Log warning explicitly; old SDK lacks the intended method boundary, so safe skip is preferred over import crash. |

## Acceptance Criteria

- [ ] Under ambient `python3` with `claude-agent-sdk 0.1.81`, importing `core.execution.agent_sdk` does not replace native `SubprocessCLITransport.close()` when graceful close is detected.
- [ ] A reproduction snippet that creates a transport-like object without `_stderr_task_group` and calls the patched close no longer raises `AttributeError`.
- [ ] Legacy patched close still waits after stdin EOF before terminating the process.
- [ ] Legacy patched close cancels either `_stderr_task_group` or `_stderr_task` when present.
- [ ] Windows Query patch path skips cleanly when `Query.wait_for_result_and_end_input` is absent.
- [ ] `python3 -m pytest -q tests/unit/execution/test_sdk_patch.py tests/unit/execution/test_agent_sdk.py tests/unit/execution/test_agent_sdk_resume_timeout.py tests/unit/test_sdk_process_cleanup.py` passes.
- [ ] After restarting Sakura, new logs no longer show `_stderr_task_group` AttributeError or `Stream retry exhausted` caused by `transport.close()` teardown.

## References

- `core/execution/_sdk_patch.py:53` — stale direct `_stderr_task_group` private attribute read.
- `core/execution/_sdk_patch.py:94` — global replacement of `SubprocessCLITransport.close`.
- `core/execution/_sdk_patch.py:153` — unconditional patch entry point.
- `core/execution/agent_sdk.py:46` — imports `apply_sdk_transport_patch`.
- `core/execution/agent_sdk.py:48` — applies SDK patch at import time.
- `core/execution/agent_sdk.py:701` — wraps streaming exceptions as `StreamDisconnectedError`.
- `core/_agent_cycle.py:1063` — retry loop catches streaming exceptions.
- `core/_agent_cycle.py:1079` — stream retry exhaustion path.
- `pyproject.toml:24` — loose `claude-agent-sdk>=0.1.40` dependency.
- `uv.lock:827` — repository lock for `claude-agent-sdk 0.1.44`.
- `/home/main/.local/lib/python3.14/site-packages/claude_agent_sdk/_internal/transport/subprocess_cli.py:71` — SDK `0.1.81` uses `_stderr_task`.
- `/home/main/.local/lib/python3.14/site-packages/claude_agent_sdk/_internal/transport/subprocess_cli.py:563` — SDK `0.1.81` native graceful wait behavior.
- `/home/main/.local/lib/python3.14/site-packages/claude_agent_sdk/_internal/query.py:827` — SDK `0.1.81` `wait_for_result_and_end_input()` stdin close.
- `docs/issues/20260310_sdk-session-text-loss-on-streaming-close.md` — original rationale for adding the graceful close patch.
- https://code.claude.com/docs/en/agent-sdk/python — Claude Agent SDK Python lifecycle documentation.
