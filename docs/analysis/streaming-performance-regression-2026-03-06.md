# Streaming Performance Regression Analysis (2026-03-06)

**Baseline commit:** `8c2d2bf2` (last commit before 2026-03-01)  
**Symptom:** Streaming feels "stuttery/jerky" compared to 5 days ago. Subordinate activity relay feature suspected.

---

## 1. Old vs New Rendering Pipeline

### OLD Pipeline (pre-subordinate feature)

**chat-stream.js**
- `onTextDelta` → `callbacks.onTextDelta?.(data.text || "")` — no batching
- Logging: `logger.info` on every 20th text_delta, chunk logs every 50 events

**streaming-controller.js**
- `onTextDelta: text => { streamingMsg.text += text; renderBubble(); }` — **render on EVERY delta**
- `renderBubble()` → `ctx.controllers.renderer.renderStreamingBubble(streamingMsg)` — no zone parameter
- No RAF batching, no `_scheduleRender`

**chat-renderer.js**
- `renderStreamingBubble(msg)` → `bubble.innerHTML = renderStreamingBubbleInner(msg, opts)`
- Full bubble replacement every call

**render-utils.js — OLD `renderStreamingBubbleInner`**
```javascript
// Flat structure: thinking + main + tool. NO zones.
let mainHtml = "";
if (msg.heartbeatRelay) { ... }
else if (msg.text) { mainHtml = renderMarkdown(msg.text, opts.animaName); }
else { mainHtml = '<span class="cursor-blink"></span>'; }
let html = `${thinkingHtml}${mainHtml}`;
if (msg.activeTool) html += `<div class="tool-indicator">...`;
return html;
```

**Characteristics:**
- 50–200+ `renderStreamingBubble` calls per second during fast streaming
- Each call: full `bubble.innerHTML = ...` (entire bubble)
- Simple flat HTML: thinking + text + tool
- No zone divs, no `querySelector`, no subordinate handling

---

### NEW Pipeline (current)

**chat-stream.js**
- Added `tool_detail`, `compression_start`, `compression_end` events
- `onToolStart` / `onToolEnd` now pass `{ tool_id, tool_name, result_summary, ... }`
- Logging reduced to `logger.debug` (less I/O)
- No structural change to text_delta handling

**streaming-controller.js**
- `onTextDelta` → `_scheduleRender(streamingMsg, "text")` — **RAF batching**
- `_scheduleRender` coalesces deltas into one render per frame (~60/sec max)
- `renderBubble(msg, zone)` — zone-specific updates
- **NEW:** `document.addEventListener("anima-tool-activity", _onSubordinateActivity)` for subordinate relay
- **NEW:** `onToolDetail`, `onCompressionStart`, `onCompressionEnd` callbacks
- **NEW:** `toolHistory` array, `tool_detail` throttling (200ms)

**chat-renderer.js**
- `renderStreamingBubble(msg, zone)` → `updateStreamingZone(bubble, msg, opts, zone)`
- Zone parameter: `"text" | "tools" | "subordinate" | "thinking" | "all"`

**render-utils.js — NEW `renderStreamingBubbleInner`**
```javascript
// ALWAYS creates 4 zone divs, even when no subordinates
return `<div class="streaming-zone-text">${_renderTextZoneContent(msg, opts)}</div>`
  + `<div class="streaming-zone-tools">${_renderToolZoneContent(msg, opts)}</div>`
  + `<div class="streaming-zone-subordinate">${_renderSubordinateZoneContent(msg, opts)}</div>`
  + `<div class="streaming-zone-thinking">${_renderThinkingZoneContent(msg, opts)}</div>`;
```

**Characteristics:**
- ~60 `updateStreamingZone` calls per second (RAF-limited)
- Zone-specific updates: only text zone touched on text_delta
- 4 zone divs always present
- `querySelector('.streaming-zone-text')` on every text update
- Fast path exists but rarely triggers (see below)

---

## 2. Initial Bubble Creation Mismatch

**Critical:** The initial streaming bubble is created by `renderChat()` → `renderLiveBubble()`, which does **NOT** use the zone structure:

```javascript
// renderLiveBubble creates:
bubble = `<div class="chat-bubble assistant streaming">${actionsHtml}${content}${imagesHtml}${compressionHtml}${toolHtml}${thinkingHtml}${tsHtml}</div>`;
// NO streaming-zone-* divs
```

When the **first** `updateStreamingZone(bubble, msg, opts, "text")` runs:
- `bubble.querySelector('.streaming-zone-text')` → **null**
- Fallback: `bubble.innerHTML = renderStreamingBubbleInner(msg, opts)` — **full replacement**
- Entire bubble content is replaced with the 4-zone structure

**Effect:** One extra full innerHTML replacement on the first text_delta. Minor, but adds a flash/reflow.

---

## 3. Zone Structure Overhead (Runs on EVERY text_delta)

**Q: Does `renderStreamingBubbleInner` always create all 4 zone divs even when there are no subordinates?**

**A: YES.** The function unconditionally returns:
```javascript
`<div class="streaming-zone-text">...</div>`
+ `<div class="streaming-zone-tools">...</div>`
+ `<div class="streaming-zone-subordinate">...</div>`   // empty when no subs
+ `<div class="streaming-zone-thinking">...</div>`;
```

So every streaming bubble has 4 wrapper divs. CSS hides empty ones (`:empty { display: none }`), but the DOM nodes are still created and present.

**Per text_delta (when zone exists):**
1. `bubble.querySelector('.streaming-zone-text')` — DOM query
2. `el.innerHTML = _renderTextZoneContent(msg, opts)` — full markdown re-render + innerHTML

---

## 4. Fast Path Analysis

```javascript
// Fast path conditions (all must hold):
if (zone === "text" && msg.streaming && msg.text && msg._mdCache) {
  const c = msg._mdCache;
  const now = performance.now();
  if ((now - c.t < _MD_RERENDER_MS) && (msg.text.length - c.len < _MD_RERENDER_CHARS)) {
    const tailEl = el.querySelector(".streaming-tail");
    if (tailEl) {
      tailEl.textContent = msg.text.slice(c.len);  // append raw text, skip markdown
      return;
    }
  }
}
// _MD_RERENDER_MS = 80, _MD_RERENDER_CHARS = 40
```

**When does the fast path trigger?**
- `msg._mdCache` exists (set only after a full `_renderTextZoneContent` run)
- Less than 80ms since last full render
- Fewer than 40 chars added since last full render
- `.streaming-tail` element exists

**Why it rarely triggers:**
- RAF batches multiple deltas. One render per frame often sees 50–100+ chars accumulated.
- `msg.text.length - c.len` frequently exceeds 40.
- So we almost always fall through to `el.innerHTML = _renderTextZoneContent(msg, opts)` — full markdown re-render.

**Fast path also has a correctness issue:** It appends raw text (`msg.text.slice(c.len)`) to `.streaming-tail`, so markdown syntax (e.g. `**bold**`) appears as plain text until the next full render.

---

## 5. `updateStreamingZone` Full innerHTML When Fast Path Fails

When the fast path does not match:
```javascript
el.innerHTML = _renderTextZoneContent(msg, opts);
```

`_renderTextZoneContent` always calls `renderMarkdown(msg.text, opts.animaName)` for the full text. So we do:
- Full markdown parse + HTML generation
- Full innerHTML replacement of the text zone

The old code did the same (`renderMarkdown` on full text + full bubble innerHTML). The new code replaces a smaller subtree (text zone only), which should be cheaper. The main cost is still `renderMarkdown`.

---

## 6. Subordinate Activity Overhead (When No Subordinates)

**`anima-tool-activity` listener:**
- Added at start of `sendChat`, removed in `onFinally`
- Fires for any tool activity from any anima
- Handler: `if (!_descendants.has(subName)) return;` — early exit when anima has no subordinates
- `_descendants = getDescendants(name, state.animas)` — computed once per stream

**Conclusion:** For animas without subordinates, the listener adds minimal overhead (one Set lookup per event). The zone structure and `_renderTextZoneContent` cost dominate.

---

## 7. Summary: Where Unnecessary Overhead Was Added

| Change | Runs on every text_delta? | Impact |
|--------|---------------------------|--------|
| 4 zone divs always created | Yes (after first update) | Extra DOM nodes, `querySelector` per update |
| `querySelector('.streaming-zone-text')` | Yes | Extra DOM query per update |
| RAF batching | Yes | Fewer updates (60/sec vs 100+/sec) — should help |
| Fast path rarely triggers | Yes | Full markdown re-render almost every frame |
| Initial bubble uses `renderLiveBubble` (no zones) | First delta only | One full replacement to switch to zone structure |
| `anima-tool-activity` listener | Only when event fires | Low for non-supervisors |
| `toolHistory` / `tool_detail` | Only on tool events | Not on text_delta |

---

## 8. Recommendations

### High impact

1. **Relax fast path thresholds** so it triggers more often:
   - Increase `_MD_RERENDER_CHARS` from 40 to 80–120
   - Increase `_MD_RERENDER_MS` from 80 to 120–150 ms

2. **Avoid zone structure when there are no subordinates:**
   - If `!msg.subordinateActivity || Object.keys(msg.subordinateActivity).length === 0`, use the old flat `renderStreamingBubbleInner` (thinking + text + tool, no zones).
   - Only create the 4-zone structure when subordinate activity is possible.

3. **Align initial bubble with zone structure:**
   - For streaming messages, use `renderStreamingBubbleInner` (zoned) in `renderLiveBubble` instead of the current flat content, so the first `updateStreamingZone` finds the zone and avoids a full replacement.

### Medium impact

4. **Fix fast path correctness:** When using the fast path, either:
   - Render the delta as markdown before appending, or
   - Accept raw text and document it as a trade-off for performance.

5. **Reduce `querySelector` cost:** Cache the text zone element on the bubble (e.g. `bubble._textZoneEl`) after the first lookup.

### Lower priority

6. **Tool activity timeline:** `renderToolActivityTimeline` is heavier than the old single `tool-indicator` div. Consider a simpler UI when `toolHistory` has only one entry.

---

## 9. Code References

- **Old `renderStreamingBubbleInner`:** `git show 8c2d2bf2:server/static/shared/chat/render-utils.js` (lines ~225–260)
- **New zone structure:** `server/static/shared/chat/render-utils.js` lines 324–328
- **`updateStreamingZone`:** `server/static/shared/chat/render-utils.js` lines 341–378
- **Fast path:** `server/static/shared/chat/render-utils.js` lines 358–369
- **Subordinate listener:** `server/static/pages/chat/streaming-controller.js` lines 297–319
