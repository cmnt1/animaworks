# Chat Streaming Performance Regression Investigation

**Date**: 2026-03-06  
**Context**: User reports streaming was faster "until the pane split" (~3 days ago, around March 2, 2026).

## Executive Summary

The pane split commit (`5c8f3614`) introduced multi-pane architecture that, combined with subsequent features (live tool activity, zone-based DOM updates, tool_detail events), created several performance hotspots. The most likely causes of the regression are:

1. **Per-pane polling** — Every pane runs its own 5-second `pollSelectedChat()` interval, multiplying API calls and DOM work
2. **`resumeActiveStream` lacks RAF batching** — The perf fix (cda90a4c) added RAF to `sendChat` but `resumeActiveStream` still calls `renderIfVisible()` on every text delta (O(n²) with `marked.parse`)
3. **Increased event volume** — `tool_detail` SSE events + subordinate activity broadcast add more DOM updates per second
4. **Stream registry tool_history** — Per-event list mutations and reversed iteration on every tool_detail/tool_end

---

## 1. Chronological Commits Since Pane Split (5c8f3614)

| Commit | Date | Summary | Performance Impact |
|--------|------|---------|---------------------|
| **5c8f3614** | Mar 2 | feat: implement multi-pane split view for chat page | **HIGH** — Per-pane polling, N× controllers |
| e4932291 | Mar 2 | fix: resolve multi-pane chat bugs and improve robustness | Low |
| cd06efa5 | Mar 3 | feat: persist per-pane anima/thread selection across reloads | Low |
| 8b3b76dc | Mar 3 | fix: prevent pane auto-focus on stream end, add flash notification | Low |
| 9a4d6b8c | Mar 3 | fix: prevent mic button presence from shifting send button layout | Low |
| d9f24422 | Mar 3 | feat: add anima avatar display to chat bubbles | **MEDIUM** — More DOM per bubble |
| c65e48ec | Mar 3 | feat: add frontend image resize & cache module for avatar thumbnails | Low |
| cd6153eb | Mar 3 | feat: per-Anima Chatwork write token + fix streaming-controller container ref | Low |
| **bcfb2466** | Mar 4 | feat: implement live tool activity streaming — tool_detail SSE + subordinate activity broadcast | **HIGH** — New SSE events, WebSocket broadcasts, anima-tool-activity listener |
| **53a844ab** | Mar 4 | perf: zone-based partial DOM updates for streaming chat bubbles | **MEDIUM** — Zone logic adds complexity; may help or hurt |
| e4bec815 | Mar 4 | fix: filter subordinate activity to prevent global tool_use event leakage | Low |
| cfaea5b4 | Mar 4 | fix: filter subordinate tool activity by org hierarchy on frontend | Low |
| f05aeb9d | Mar 4 | refactor: simplify streaming-controller and session-manager | Reverted |
| **035b9828** | Mar 4 | Revert "refactor: simplify streaming-controller and session-manager" | Restored complexity |
| **cda90a4c** | Mar 6 | perf: fix streaming chat display jank — RAF batching, log reduction, SSE flush | **FIX** — Partial; sendChat only |
| c87b8a60 | Mar 6 | fix: remove stale lastChunkTime reference in chat-stream.js | Low |

---

## 2. Specific Diff Sections Most Likely to Cause Slowdown

### 2.1 Per-Pane Polling (pane-host.js, 5c8f3614)

**Location**: `server/static/pages/chat/pane-host.js` lines 176–180

```javascript
const chatInterval = setInterval(
  () => ctx.controllers.renderer.pollSelectedChat(),
  CONSTANTS.CHAT_POLL_INTERVAL_MS,  // 5000ms
);
pane.intervals.push(chatInterval);
```

**Impact**: Each pane runs `pollSelectedChat()` every 5 seconds. With 2 panes = 2× API calls (`fetchConversationHistory` + `api(/sessions)`), 2× `mergePolledHistory`, 2× potential `renderChat()`. With 4 panes = 4× load. Polling runs even when a pane is not focused.

### 2.2 resumeActiveStream — No RAF Batching (streaming-controller.js)

**Location**: `server/static/pages/chat/streaming-controller.js` lines 383–388

```javascript
onTextDelta: text => {
  if (streamingMsg?.streaming) {
    streamingMsg.text += text;
    renderIfVisible(streamingMsg);  // ← Called on EVERY delta, no RAF
  }
},
onThinkingDelta: text => {
  if (streamingMsg?.streaming) {
    streamingMsg.thinkingText = (streamingMsg.thinkingText || "") + text;
    renderIfVisible(streamingMsg);  // ← Same
  }
},
```

**Impact**: The perf fix (cda90a4c) added RAF batching to `sendChat` callbacks, but `resumeActiveStream` (used when reloading a page with an active stream) still invokes `renderIfVisible` → `renderStreamingBubble` → `renderMarkdown(fullText)` on every delta. With 50 deltas/sec, that's 50× `marked.parse()` per second = O(n²) cost.

### 2.3 Live Tool Activity — New Event Volume (bcfb2466)

**Backend** (`server/routes/chat.py`): Emits `tool_detail` SSE events and WebSocket `anima.tool_activity` for every tool start/detail/end.

**Frontend** (`streaming-controller.js`): Global listener:

```javascript
document.addEventListener("anima-tool-activity", _onSubordinateActivity);
```

**Impact**: Each tool execution now produces multiple events (tool_start, tool_detail×N, tool_end). Subordinate activity broadcasts to all open panes. More events → more `renderBubble(streamingMsg, "subordinate")` and `_throttledSubRender` calls.

### 2.4 stream_registry tool_history (server/stream_registry.py)

**Location**: `ResponseStream.add_event()` for `tool_detail` and `tool_end`

```python
elif event == "tool_detail":
    tid = payload.get("tool_id", "")
    for entry in reversed(self.tool_history):  # O(n) per tool_detail
        if entry.get("tool_id") == tid and not entry.get("completed"):
            entry["detail"] = payload.get("detail", "")
            break
elif event == "tool_end":
    # Similar reversed iteration
```

**Impact**: Every tool_detail and tool_end does a reversed list scan. With many tools, this adds per-event overhead. Minor compared to frontend, but contributes.

### 2.5 Zone-Based Partial DOM (53a844ab)

**Location**: `server/static/shared/chat/render-utils.js` — `updateStreamingZone()`

The streaming bubble is split into 4 zones: text, tools, subordinate, thinking. Each zone is updated via targeted `innerHTML` instead of full re-render.

**Impact**: Intended to reduce work, but:
- Zone lookup (`querySelector` for each zone) adds overhead
- Multiple small DOM writes can cause layout thrashing if not batched
- The `_scheduleRender` RAF in sendChat helps, but zone selection logic (`_rafZone`) adds branching

### 2.6 SSE Flush (cda90a4c) — Mitigation

**Location**: `server/routes/chat.py` in `_sse_tail`

```python
for event in events:
    yield format_sse_with_id(event.event, event.payload, event.event_id)
    seq = event.seq
await asyncio.sleep(0)  # Yield control so ASGI can flush
```

**Impact**: Positive. Allows the ASGI server to flush chunks instead of buffering. Reduces perceived latency.

---

## 3. Smoking Gun Changes

### Primary: Per-Pane Polling + resumeActiveStream Gap

1. **Pane split** introduced N independent chat contexts, each with its own 5-second polling. Even with a single visible pane, multiple panes multiply background work.

2. **resumeActiveStream** was never updated with RAF batching. When a user reloads or switches back to a tab with an active stream, the resume path triggers a full render on every delta. This path is separate from `sendChat` and was missed by the perf fix.

### Secondary: Event Volume Increase

3. **Live tool activity** (bcfb2466) added `tool_detail` events and subordinate broadcasts. A single tool call can now emit 5–10+ events instead of 2 (start + end). Each event triggers frontend updates.

### Tertiary: Container-Scoped DOM Queries

4. The pane split replaced `document.getElementById("chatXxx")` with `ctx.state.container.querySelector('[data-chat-id="chatXxx"]')`. QuerySelector is slower than getElementById, though the difference is usually small. With multiple panes, each pane does its own queries.

---

## 4. Configuration Changes (index.html)

- No new scripts loaded
- Cache-buster version bumps only (`app.js`, `chat.css`, `responsive.css`, etc.)
- No new CSS that would cause layout thrashing

---

## 5. Workspace Split Implementation

- **pane-host.js**: Creates up to 4 panes, each with full controller set (anima, thread, renderer, streaming, etc.)
- **splitter.js**: Pointer-event-based drag. No ResizeObserver or MutationObserver. `getBoundingClientRect()` on pointermove during drag — could cause layout reads during interaction, but only when user is dragging
- **Workspace 3D** (`office3d.js`): Has ResizeObserver. Used on `/#/workspace`, not on `/#/chat` Dashboard. Not a factor for the chat page regression.

---

## 6. Recommended Fixes (Priority Order)

1. **Add RAF batching to `resumeActiveStream`** — Mirror the `_scheduleRender` pattern from `sendChat` for `onTextDelta` and `onThinkingDelta` in the resume path.

2. **Throttle or scope per-pane polling** — Run `pollSelectedChat` only for the focused pane, or increase interval for non-focused panes (e.g., 5s focused, 30s background).

3. **Throttle subordinate activity updates** — The 150ms throttle exists but `anima-tool-activity` can still fire frequently. Consider debouncing or coalescing.

4. **Profile `updateStreamingZone`** — Verify zone-based updates are not causing layout thrashing. If so, batch zone updates in a single RAF.

5. **Consider reducing tool_detail frequency** — Emit tool_detail only on significant changes (e.g., when detail string length crosses a threshold) rather than every chunk.

---

## 7. Verification Commands

```bash
# Commits touching streaming since pane split
git log --oneline 5c8f3614..HEAD -- server/static/pages/chat/ server/static/shared/chat-stream.js server/static/shared/chat/render-utils.js

# Full diff of streaming-related code
git diff 5c8f3614..HEAD -- server/static/ server/routes/chat.py server/stream_registry.py core/execution/
```
