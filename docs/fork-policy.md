# Fork policy — deliberate divergences from upstream

This fork (`cmnt1/animaworks`) intentionally differs from `xuiltul/animaworks`
in the places listed below.  They are **not** merge accidents: each one is a
decision we re-affirm every time upstream touches the same code.

Read this before resolving an upstream merge conflict.  If a conflict lands on
one of these lines, the answer is already here — you do not need to re-derive it.

Keep this file updated when a new deliberate divergence is introduced, and
remove entries once upstream converges with us.

---

## 1. `process_model` default stays `legacy`

**Where:** `core/config/schemas.py` (`ResolvedProcessModelConfig`),
`core/config/resolver.py` (`resolve_process_model_config`)

**Upstream:** defaults to `phase3` (task-runner isolation + root DB ownership)
so new adopters get the new architecture out of the box (upstream `ab0a973a`).

**Us:** defaults to `legacy`.  We run an existing fleet; syncing upstream must
never implicitly change a running anima's process topology.  Migration is done
per anima by writing `process_model` into `status.json` explicitly — `phase2`
and `phase3` remain fully available that way.

**On conflict:** keep `legacy` as the default; take upstream's changes to the
`phase2`/`phase3` branches themselves.

---

## 2. Notion is disabled by default

**Where:** `templates/{en,ja,ko}/roles/*/permissions.json`,
`templates/*/anima_templates/_blank/permissions.json`

**Upstream:** ships `notion` in `external_tools.allow`.

**Us:** `notion` is listed in `external_tools.deny` for every role.  Notion is
no longer used here — the workflow moved to Obsidian (fork commit `745ab66b`,
"Remove default Notion access for Animas", later extended to the remaining
roles).  Note that `deny` always wins in `core/tooling/permissions.py`, so an
`allow` entry alone is inert — but leaving it in place is misleading, so we
drop it.

Because these templates use `external_tools.allow_all: true`, an *absent*
`deny` entry means Notion is reachable.  The opt-out has to be explicit.

**On conflict:** do not add `notion` to `allow`.  Take any *other* tool
additions upstream makes in the same list (e.g. `github_create-*`).

**Pinned by:** `tests/unit/test_fork_policy.py`

---

## 3. `/animas` stays a first-class page

**Where:** `server/static/modules/router.js` (`REDIRECTS`, route table),
`server/static/index.html` (sidebar nav), `server/static/pages/animas.js`

**Upstream:** is folding list views into the home org chart — the bare
`#/animas` list is gone and `/processes` and `/server` redirect to `#/`.
Detail routes (`#/animas/<name>`) still resolve.

**Us:** `/animas` is a full Anima management page (sorting, filtering, model
and activity columns) and is roughly twice the size of upstream's version.  We
also ship a fork-only `/sns-search` page.  Redirects point at our pages:
`/processes` → `#/animas`, `/server` → `#/scheduler`.

**On conflict:** keep our nav entries, redirects and route table.  Upstream's
deletions in `animas.js` are "upstream removed the list view", not "upstream
replaced our code" — the conflicting upstream side is usually empty.

---

## 4. Process liveness must not use `os.kill`

**Where:** `core/platform/processing_lease.py` (`_pid_exists`),
`core/platform/process.py` (`is_process_alive`)

**Upstream:** probes with `os.kill(pid, 0)`.

**Us:** probes with the psutil-backed `is_process_alive`.  On Windows
`os.kill` maps to `TerminateProcess`, so `os.kill(pid, 0)` **kills the very
process it is checking**.  This fork is Windows-hosted, so upstream's form is
not merely inaccurate — it is destructive.

**On conflict:** take upstream's lease schema/classification changes, but keep
the psutil probe.  Preserve the three-valued result (`True`/`False`/`None`):
`None` means "uncertain", which keeps a live lease from being reclaimed.

---

## 5. `DigitalAnima` import in the runner stays deferred

**Where:** `core/supervisor/runner.py`

**Upstream:** imports `DigitalAnima` at module level.

**Us:** imports it lazily inside `start()`, with the type-only import under
`TYPE_CHECKING`.  Loading `DigitalAnima` pulls in the RAG/model stack (~4.5s
warm, far worse on a cold disk); keeping it out of module import lets the IPC
socket bind immediately so the parent's socket-wait window is not consumed by
model loading.  Related fork setting: `server.anima_socket_create_timeout`.

**On conflict:** keep the deferred import; take upstream's other additions to
the same import block.

---

## Windows compatibility (recurring, not a policy divergence)

Upstream develops and runs CI on Linux (`ubuntu-latest`), so Linux-only
constructs land regularly and fail here: `os.killpg`, `/proc` parsing,
`os.symlink` (needs privilege), `chmod` (no-op), `termios`/`pty`, and
`time.monotonic()`'s ~15.6 ms resolution.

Convention: guard the affected test with the existing idiom rather than
changing behaviour, so coverage is retained on CI:

```python
@pytest.mark.skipif(os.name == "nt", reason="...")
```

Fix the test instead of skipping when the flake is a resolution/ordering
artifact that can be made platform-independent (see
`tests/unit/core/supervisor/test_task_runner_hang_busy.py`).
