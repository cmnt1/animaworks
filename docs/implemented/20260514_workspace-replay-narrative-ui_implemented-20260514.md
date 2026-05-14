# Workspace Replay Narrative UI — Show who did what, for whom, and why

## Overview

Replay must make the workspace understandable at a glance. After replay data is complete and semantic events exist, the org dashboard should show a narrative layer that explains the current action, actor, target, group, and progress while replay runs or seeks.

Depends on:

- `docs/issues/20260514_workspace-replay-foundation.md`
- `docs/issues/20260514_workspace-replay-semantic-events.md`

## Problem / Background

### Current State

- The replay control bar provides time controls but does not explain what is currently happening.
- Cards display short stream entries, but replay lacks a primary "current action" surface.
- Message/delegation/external lines are transient and do not provide stable context after a seek.
- 3D timeline replay is a single-event highlight and does not communicate a sequence.

Relevant code:

- `server/static/workspace/modules/replay-ui.js:88` — replay bar DOM construction.
- `server/static/workspace/modules/replay-ui.js:220` — time display update.
- `server/static/workspace/modules/org-dashboard.js:560` — replay line duration scaling.
- `server/static/workspace/modules/org-dashboard.js:1278` — replay startup wiring.
- `server/static/workspace/modules/org-dashboard.js:1411` — seek rebuild updates cards/KPI only.
- `server/static/workspace/modules/timeline-history.js:65` — timeline history fetches flat pages.
- `server/static/workspace/modules/timeline-replay.js:37` — timeline replay highlights one clicked event.
- `server/static/workspace/style.css:4078` — existing replay bar styles.

### Root Cause

1. Replay UI exposes transport controls but no semantic state summary — `server/static/workspace/modules/replay-ui.js:97`.
2. Seek rebuild updates card streams but does not surface the current or nearest semantic event as narrative context — `server/static/workspace/modules/org-dashboard.js:1411`.
3. Lines are visual effects, not persistent explanation — `server/static/workspace/modules/org-dashboard.js:560`.

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `replay-ui.js` | Direct | No current-action panel exists. |
| `replay-engine.js` | Direct | Does not expose current semantic context to UI callbacks. |
| `org-dashboard.js` | Direct | Rebuild renders cards/KPI but not narrative state. |
| `style.css` | Direct | Replay UI lacks layout for narrative state. |

## Decided Approach / 確定方針

### Design Decision

確定: add a compact narrative band directly below the replay controls. The band will be driven only by semantic replay events from Issue 2. It will show the nearest semantic event at or before the current replay time, the actor, target, group identity, status, event count progress, and suppressed raw event count. It will not render raw tool logs as primary text.

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Add a long chronological feed beside the org chart | Detailed | Competes with cards and makes replay dense without clarifying the current moment | **Rejected**: replay needs a stable current-action summary first. |
| Depend only on animated lines | Visually simple | Lines disappear and do not explain group/task context after seek | **Rejected**: narrative state must remain visible. |
| Put narrative text inside every Anima card only | Local context | Cross-Anima handoffs and group identity are hard to follow | **Rejected**: one global narrative band is required. |
| Build a new landing-style replay page | More space | Splits the user away from the workspace they are trying to understand | **Rejected**: replay belongs inside the org workspace. |

### Key Decisions from Discussion

1. **Narrative UI consumes semantic events only** — Reason: raw logs are the source of the current confusion.
2. **Global current-action band is required** — Reason: users need a stable explanation independent of transient animations.
3. **Cards show semantic summaries** — Reason: each Anima should show readable work state, not tool fragments.
4. **Lines are derived from semantic actor/target data** — Reason: direction must stay correct after historical seek.
5. **The UI remains operational, not a marketing surface** — Reason: workspace is a work dashboard.

### Narrative Band Contract

Add a DOM area with this structure:

```html
<div class="org-replay-narrative" id="orgReplayNarrative">
  <div class="org-replay-narrative-main">
    <span class="org-replay-narrative-kind"></span>
    <span class="org-replay-narrative-label"></span>
    <span class="org-replay-narrative-summary"></span>
  </div>
  <div class="org-replay-narrative-meta">
    <span class="org-replay-narrative-route"></span>
    <span class="org-replay-narrative-group"></span>
    <span class="org-replay-narrative-status"></span>
    <span class="org-replay-narrative-count"></span>
  </div>
</div>
```

Required display behavior:

| Element | Content |
|---------|---------|
| `kind` | Semantic kind label, for example `Delegation`, `Task`, `Channel`, `Heartbeat`, `Error`. |
| `label` | Current semantic event `label`. |
| `summary` | Current semantic event `summary`. Empty summaries hide this span. |
| `route` | `actor -> target` when both exist; actor only when target is empty. |
| `group` | `group_type` plus shortened `group_id`. |
| `status` | `started`, `progress`, `completed`, or `failed`. |
| `count` | `currentIndex + 1 / totalEvents`, plus suppressed count when greater than zero. |

When no semantic event exists at the current time, show:

- `kind`: `Replay`
- `label`: `No activity at this time`
- all other spans empty except count.

### Engine/UI State Contract

`ReplayEngine` must call a new callback:

```js
onNarrativeUpdate({
  currentTimeMs,
  currentEvent,
  currentIndex,
  totalEvents,
  visibleEventsInLastHour,
  activeGroupId,
  activeGroupType,
  suppressedCount,
});
```

Rules:

- `currentEvent` is the latest semantic event with `eventTimeMs(event) <= currentTimeMs`.
- `currentIndex` is the index of `currentEvent` in the semantic events array, or `-1` when none exists yet.
- `visibleEventsInLastHour` counts semantic events with `importance >= 2`.
- `suppressedCount` is the sum of `debug.suppressed_count` for events at the current `group_id`; it is `0` when no group is active.

### Card and Line Rendering Rules

| Semantic kind | Card stream type | Line behavior |
|---------------|------------------|---------------|
| `message` | `msg_out` when actor is card Anima, `msg_in` when target is card Anima | Draw internal line when actor and target are both Anima cards. |
| `delegation` | `task` | Draw delegation line when actor and target are both Anima cards. |
| `external` | `board` | Draw external line to tool/channel when target is not an Anima card. |
| `channel` | `board` | Draw channel/external line only when target channel is present. |
| `task` | `task` | No line unless semantic event also has target Anima. |
| `heartbeat` | `heartbeat` | No line. |
| `cron` | `cron` | No line. |
| `error` | `error` | No line unless target exists. |
| `memory` | `memory` | No line. |
| `tool` | `tool` | No line. |
| `other` | `tool` | Hidden in normal replay because `importance < 2`. |

Line text uses semantic `summary`. Card text uses semantic `label` plus `summary` when space allows.

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `server/static/workspace/modules/replay-engine.js` | Modify | Track current semantic event during play and seek. Invoke `onNarrativeUpdate` after load, seek, every replay event batch, and completion. |
| `server/static/workspace/modules/replay-ui.js` | Modify | Render narrative band, add `updateNarrative(state)` and clear narrative state on dispose. |
| `server/static/workspace/modules/org-dashboard.js` | Modify | Wire engine `onNarrativeUpdate` to `ReplayUI.updateNarrative()`. Use semantic line rules for replay events and seek rebuild. |
| `server/static/workspace/style.css` | Modify | Add responsive styles for `.org-replay-narrative`, using stable dimensions and wrapping text without overlap. |
| `tests/unit/frontend/test_replay_feature.py` | Modify | Add source-level assertions for narrative DOM, callback wiring, semantic card rendering, and line derivation from semantic actor/target. |
| `tests/e2e/test_replay_feature_e2e.py` | Modify | Add a workspace replay smoke test that loads semantic replay, seeks, and verifies narrative text is present. |

## Implementation Plan

### Phase 1: Engine Narrative State

| # | Task | Target |
|---|------|--------|
| 1-1 | Add `onNarrativeUpdate` constructor option | `replay-engine.js` |
| 1-2 | Implement `_buildNarrativeState(currentTimeMs)` | `replay-engine.js` |
| 1-3 | Call narrative update after load, seek, tick batches, and completion | `replay-engine.js` |

**Completion condition**: source tests assert `onNarrativeUpdate` exists and is called from seek and tick paths.

### Phase 2: Replay UI Narrative Band

| # | Task | Target |
|---|------|--------|
| 2-1 | Add narrative DOM below controls | `replay-ui.js` |
| 2-2 | Add `updateNarrative(state)` with empty-state behavior | `replay-ui.js` |
| 2-3 | Add responsive CSS with fixed minimum heights and wrapping | `style.css` |

**Completion condition**: narrative band is visible in replay mode and does not shift the org chart unpredictably during text changes.

### Phase 3: Semantic Card and Line Rendering

| # | Task | Target |
|---|------|--------|
| 3-1 | Render card streams from semantic event kind/label/summary | `org-dashboard.js` |
| 3-2 | Draw semantic lines from actor/target/line_type | `org-dashboard.js` |
| 3-3 | Ensure seek rebuild redraws stable semantic context | `org-dashboard.js` |

**Completion condition**: seeking to a delegated message shows a delegation line and narrative route with actor and target present.

### Phase 4: Tests

| # | Task | Target |
|---|------|--------|
| 4-1 | Add source tests for narrative methods and markup | `tests/unit/frontend/test_replay_feature.py` |
| 4-2 | Add source tests for semantic line mapping | `tests/unit/frontend/test_replay_feature.py` |
| 4-3 | Add E2E smoke test for replay narrative render | `tests/e2e/test_replay_feature_e2e.py` |

**Completion condition**: replay test suite covers narrative rendering, semantic cards, and line direction.

## Scope

### In Scope

- Narrative band in org replay mode.
- Engine callback for current semantic state.
- Semantic card stream display during replay.
- Semantic line rendering during play and seek.
- Responsive CSS for narrative layout.
- Tests for narrative UI behavior.

### Out of Scope

- Backend semantic projection — handled by `20260514_workspace-replay-semantic-events.md`.
- Replay API completeness and WebSocket buffering — handled by `20260514_workspace-replay-foundation.md`.
- New 3D replay sequence system — excluded because this issue targets org workspace replay.
- Long-form replay transcript export — excluded to keep the first UI improvement focused on live understanding.

## Edge Cases

| Case | Handling |
|------|----------|
| No semantic events in selected range | Show `Replay` / `No activity at this time`; cards remain idle. |
| Current event has long label or summary | Clamp label to one line, summary to two lines with CSS wrapping and overflow handling. |
| Actor exists but target does not | Route displays actor only and no line is drawn. |
| Target is a channel | Route displays `actor -> #channel`; channel/external line uses existing external-line rendering. |
| Current event has `importance=1` | Narrative skips it and uses the nearest previous event with `importance >= 2`; if none exists, show empty state. |
| Seek lands between groups | Narrative keeps the latest visible semantic event before the seek time. |
| Replay reaches end | Narrative remains on the final visible semantic event and play state becomes paused. |

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Narrative text overlaps controls on small screens | Replay UI becomes harder to use | Use stable min-height, CSS grid wrapping, and no viewport-width font scaling. |
| Too much text makes replay feel noisy | The clarity problem remains | Show one current event, compact meta, and rely on cards for local context. |
| Semantic line rendering duplicates transient lines | Visual clutter | Draw lines only for current playback events and seek-selected current event; clear old lines during seek rebuild. |
| Narrative state becomes stale after seek | User sees wrong current action | `seek()` must invoke `onNarrativeUpdate` after cursor rebuild every time. |

## Acceptance Criteria

- [ ] Replay mode shows `.org-replay-narrative` below the replay controls.
- [ ] Narrative band displays semantic kind, label, actor/target route, group, status, and event count.
- [ ] When no visible semantic event exists, narrative shows `Replay` and `No activity at this time`.
- [ ] Seeking updates narrative state immediately.
- [ ] Playback updates narrative state as events advance.
- [ ] Replay cards render semantic labels and summaries rather than raw `tool_use` / `tool_result` fallback text.
- [ ] Delegation semantic events draw delegation lines with actor and target present.
- [ ] Message semantic events draw internal lines when both endpoints are Anima cards.
- [ ] External/channel semantic events draw external/channel lines without pretending the target is an Anima.
- [ ] Narrative CSS does not overlap controls or cards at desktop and mobile widths covered by existing E2E viewport tests.
- [ ] Tests pass: `uv run pytest tests/unit/frontend/test_replay_feature.py tests/e2e/test_replay_feature_e2e.py -q`.

## References

- `server/static/workspace/modules/replay-ui.js:88` — replay UI DOM construction.
- `server/static/workspace/modules/replay-ui.js:220` — replay time update method.
- `server/static/workspace/modules/replay-engine.js:199` — seek rebuild path.
- `server/static/workspace/modules/org-dashboard.js:560` — replay line duration behavior.
- `server/static/workspace/modules/org-dashboard.js:1278` — replay startup wiring.
- `server/static/workspace/modules/org-dashboard.js:1411` — seek rebuild currently updates cards/KPI only.
- `server/static/workspace/modules/timeline-history.js:65` — flat history fetch.
- `server/static/workspace/modules/timeline-replay.js:37` — single-event timeline replay.
- `server/static/workspace/style.css:4078` — existing replay bar styles.
- `docs/issues/20260514_workspace-replay-foundation.md` — dependency.
- `docs/issues/20260514_workspace-replay-semantic-events.md` — dependency.
