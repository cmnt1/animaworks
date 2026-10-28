// ── Thinking Bubble ─────────────────────────────
// While a chat reply streams, the reply bubble shows what the Anima is doing:
// bouncing dots, the current step, elapsed time, a sweeping bar and the list
// of finished (✓) / current (●) steps. When the reply text starts, the same
// bubble becomes the reply and the steps fold into "Steps n ▸" below it.
//
// State lives on the streaming message (`msg.think`), so every re-render of
// the chat rebuilds the same bubble. Everything here is DOM-free except the
// elapsed-time ticker and the delegated click handlers at the bottom.
import { t } from "../i18n.js";
import { escapeHtml } from "../html-utils.js";
import { faceUrl } from "./emotion-face.js";

const TARGET_MAX = 40;
const SAY_MAX = 160;
const RESULT_MAX = 500;
const TICK_MS = 500;

const TOOL_KINDS = {
  read: ["read", "read_file", "read_memory_file", "notebookread", "view", "view_image"],
  write: [
    "write", "edit", "multiedit", "write_file", "edit_file", "write_memory_file",
    "notebookedit", "file_change", "apply_patch",
  ],
  shell: ["bash", "shell", "execute_command", "exec_command", "command", "local_shell", "bashoutput", "killshell"],
  search: ["grep", "glob", "search_files", "glob_files", "search_memory", "ls", "list_directory"],
  web: ["web_search", "websearch", "webfetch", "web_fetch", "x_search"],
  send: ["send_message", "post_channel", "call_human"],
  delegate: ["delegate_task", "task", "agent"],
  plan: ["todowrite", "update_task", "add_task", "update_plan"],
};
const _KIND_BY_TOOL = new Map(
  Object.entries(TOOL_KINDS).flatMap(([kind, names]) => names.map(n => [n, kind])),
);

let _thinkSeq = 0;
/** Bubble ids whose step list the user collapsed (survives re-renders). */
const _collapsed = new Set();

// ── Pure helpers ────────────────────────────────

/** Seconds → "0:12" / "12:05" / "1:02:03". */
export function formatElapsed(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

function _bareToolName(toolName) {
  let name = String(toolName || "").trim();
  const mcp = name.match(/^mcp__[^_]+(?:_[^_]+)*?__(.+)$/);
  if (mcp) name = mcp[1];
  return name;
}

/** Classify a tool name into a step kind ("read", "shell", ... or "unknown"). */
export function toolKind(toolName) {
  const bare = _bareToolName(toolName);
  const kind = _KIND_BY_TOOL.get(bare.toLowerCase());
  if (kind) return kind;
  // Codex reports shell commands with the command line as the tool name.
  if (/\s/.test(bare)) return "shell";
  return "unknown";
}

/** Human-readable "what I'm doing" sentence for a tool. */
export function toolLabel(toolName) {
  const kind = toolKind(toolName);
  if (kind === "unknown") {
    return t("chat.think.tool.unknown", { tool: _bareToolName(toolName) || "tool" });
  }
  return t(`chat.think.tool.${kind}`);
}

/** Shorten a tool detail to a monospace target: path tail or first 40 chars. */
export function shortTarget(detail) {
  const text = String(detail || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  if (!text.includes(" ") && text.includes("/")) {
    const parts = text.split("/").filter(Boolean);
    const tail = parts.slice(-2).join("/");
    return tail.length > TARGET_MAX ? `…${tail.slice(-TARGET_MAX)}` : tail;
  }
  return text.length > TARGET_MAX ? `${text.slice(0, TARGET_MAX)}…` : text;
}

function _targetFromInput(input) {
  if (!input) return "";
  let obj = input;
  if (typeof input === "string") {
    try { obj = JSON.parse(input); } catch { return shortTarget(input); }
  }
  if (!obj || typeof obj !== "object") return shortTarget(String(obj));
  for (const key of ["file_path", "path", "command", "query", "pattern", "url", "to", "name", "channel"]) {
    if (obj[key]) return shortTarget(String(obj[key]));
  }
  return "";
}

// ── State transitions (operate on the streaming message) ──

/** Create a fresh thinking state. */
export function createThinkState(now = Date.now()) {
  _thinkSeq += 1;
  return {
    id: `think-${now.toString(36)}-${_thinkSeq}`,
    startedAt: now,
    phase: "thinking",
    steps: [{ kind: "think", done: false }],
  };
}

/** Attach thinking state to a streaming message (idempotent). */
export function ensureThink(msg, now = Date.now()) {
  if (msg && !msg.think) msg.think = createThinkState(now);
  return msg?.think || null;
}

function _hasBody(msg) {
  return Boolean(String(msg?.text || "").trim());
}

function _currentStep(think) {
  for (let i = think.steps.length - 1; i >= 0; i--) {
    const s = think.steps[i];
    if (s.kind !== "say" && !s.done) return s;
  }
  return null;
}

function _finishCurrent(think) {
  for (const s of think.steps) if (s.kind === "think") s.done = true;
}

/** True while the bubble should show the thinking UI instead of reply text. */
export function isThinking(msg) {
  if (!msg?.think || !msg.streaming) return false;
  if (msg.heartbeatRelay || msg.afterHeartbeatRelay) return false;
  return !_hasBody(msg);
}

/**
 * Call after appending a text_delta to `msg.text`.
 * @returns {boolean} true when the bubble switched from thinking to reply text.
 */
export function thinkOnText(msg) {
  const think = msg?.think;
  if (!think || think.phase === "writing" || !_hasBody(msg)) return false;
  think.phase = "writing";
  return true;
}

/**
 * Record a tool_start. Text streamed before the tool call is work-in-progress
 * talk, not the reply: it moves into the step list as a faint "say" line and
 * `msg.text` is cleared so only text after the last tool becomes the reply.
 * @returns {{ moved: boolean }} moved=true when reply text was moved away.
 */
export function thinkToolStart(msg, toolName, toolId = "") {
  const think = ensureThink(msg);
  if (!think) return { moved: false };
  let moved = false;
  const said = String(msg.text || "").trim();
  if (said) {
    think.steps.push({ kind: "say", text: said, done: true });
    msg.text = "";
    delete msg._displayText;
    delete msg._mdCache;
    moved = true;
  }
  _finishCurrent(think);
  think.steps.push({ kind: "tool", tool: toolName || "", toolId: toolId || "", target: "", done: false });
  think.phase = "tool";
  return { moved };
}

function _findTool(think, toolId) {
  for (let i = think.steps.length - 1; i >= 0; i--) {
    const s = think.steps[i];
    if (s.kind !== "tool" || s.done) continue;
    if (!toolId || !s.toolId || s.toolId === toolId) return s;
  }
  return null;
}

export function thinkToolDetail(msg, toolId, detail) {
  const think = msg?.think;
  if (!think) return;
  const step = _findTool(think, toolId);
  if (step && detail) step.target = shortTarget(detail);
}

export function thinkToolEnd(msg, detail = {}) {
  const think = msg?.think;
  if (!think) return;
  const step = _findTool(think, detail.tool_id);
  if (step) {
    step.done = true;
    step.error = !!detail.is_error;
    if (!step.target && detail.input_summary) step.target = shortTarget(detail.input_summary);
  }
  if (!_currentStep(think) && think.phase === "tool") think.phase = "thinking";
}

/**
 * Split the final reply from the work-in-progress talk. `reply` is the done
 * summary (which repeats every text block) or, when `aligned` is false, text
 * already limited to what came after the last tool.
 * @returns {string} reply body
 */
export function thinkDone(msg, reply, { aligned = true, emotion = null } = {}) {
  const think = msg?.think;
  const text = String(reply ?? "");
  if (!think) return text;
  const says = think.steps.filter(s => s.kind === "say");
  let body = text;
  if (aligned && says.length) {
    const rest = _stripLeading(text, says.map(s => s.text));
    if (rest !== null) {
      body = rest;
    } else {
      const tail = String(msg.text || "").trim();
      const idx = tail ? text.lastIndexOf(tail) : -1;
      body = idx >= 0 ? text.slice(idx) : (tail || text);
    }
  }
  body = body.trim();
  if (!body && says.length) {
    // The reply was written before a final tool (e.g. send_message): the last
    // "say" line is the answer, so give it back to the bubble.
    const last = says[says.length - 1];
    body = last.text;
    think.steps.splice(think.steps.lastIndexOf(last), 1);
  }
  for (const s of think.steps) s.done = true;
  think.phase = "done";
  if (emotion) think.emotion = emotion;
  return body;
}

function _stripLeading(text, segments) {
  let rest = text;
  for (const seg of segments) {
    const s = String(seg || "").trim();
    const trimmed = rest.replace(/^\s+/, "");
    if (!s || !trimmed.startsWith(s)) return null;
    rest = trimmed.slice(s.length);
  }
  return rest;
}

export function thinkError(msg) {
  const think = msg?.think;
  if (!think) return;
  for (const s of think.steps) s.done = true;
  think.phase = "error";
}

/** Settle a stream that ended without `done` (user stop, dropped stream). */
export function thinkStop(msg) {
  const think = msg?.think;
  if (!think || think.phase === "done" || think.phase === "error") return false;
  for (const s of think.steps) s.done = true;
  think.phase = "done";
  return true;
}

/**
 * Rebuild thinking state for a resumed stream from its progress snapshot
 * (`msg.toolHistory`, `msg.activeTool`, `msg.text`).
 */
export function restoreThink(msg, now = Date.now()) {
  if (!msg) return null;
  const history = Array.isArray(msg.toolHistory) ? msg.toolHistory : [];
  const starts = history.map(e => Number(e.started_at)).filter(n => Number.isFinite(n) && n > 0);
  const think = createThinkState(starts.length ? Math.min(...starts) : now);
  msg.think = think;
  if (history.length) {
    think.steps[0].done = true;
    for (const e of history) {
      think.steps.push({
        kind: "tool",
        tool: e.tool_name || "",
        toolId: e.tool_id || "",
        target: shortTarget(e.detail || e.input_summary || ""),
        done: !!e.completed,
        error: !!e.is_error,
      });
    }
    // Text seen while a tool is still running was said before that tool.
    if (msg.activeTool && _hasBody(msg)) {
      const lastIdx = think.steps.length - 1;
      think.steps.splice(lastIdx, 0, { kind: "say", text: msg.text.trim(), done: true });
      msg.text = "";
    }
  }
  think.phase = _hasBody(msg) ? "writing" : (_currentStep(think)?.kind === "tool" ? "tool" : "thinking");
  return think;
}

// ── Labels / activity ───────────────────────────

function _stepLabel(step) {
  if (step.kind === "think") return t("chat.think.thinking");
  if (step.kind === "tool") return toolLabel(step.tool);
  return step.text || "";
}

/** Count of steps shown as "Steps n" (work-in-progress talk is not a step). */
export function stepCount(think) {
  return think ? think.steps.filter(s => s.kind !== "say").length : 0;
}

/** The "what I'm doing now" sentence. */
export function currentLabel(msg) {
  const think = msg?.think;
  if (!think) return "";
  if (msg.compressing) return t("chat.compressing");
  if (think.phase === "writing" || (msg.streaming && _hasBody(msg))) return t("chat.think.writing");
  const step = _currentStep(think);
  return step ? _stepLabel(step) : t("chat.think.thinking");
}

/** Phase for the `aw:anima-activity` contract. */
export function activityPhase(msg) {
  const think = msg?.think;
  if (!think) return "thinking";
  if (think.phase === "error" || think.phase === "done") return think.phase;
  if (msg.streaming && _hasBody(msg)) return "writing";
  return _currentStep(think)?.kind === "tool" ? "tool" : "thinking";
}

/**
 * Dispatch `aw:anima-activity` when phase or label changed since the last call.
 * @returns {boolean} whether an event was dispatched
 */
export function emitThinkActivity({ anima, threadId, msg, emotion = null, force = false }) {
  const think = msg?.think;
  if (!think || !anima) return false;
  const phase = activityPhase(msg);
  const label = phase === "done" || phase === "error" ? "" : currentLabel(msg);
  const key = `${phase}\u0000${label}`;
  if (!force && think._lastEmit === key) return false;
  think._lastEmit = key;
  if (typeof document === "undefined" || typeof CustomEvent === "undefined") return false;
  document.dispatchEvent(new CustomEvent("aw:anima-activity", {
    detail: {
      anima,
      phase,
      label,
      emotion: phase === "done" ? (emotion || think.emotion || "neutral") : null,
      threadId: threadId || "default",
    },
  }));
  return true;
}

// ── HTML ────────────────────────────────────────

function _stepHtml(step, { withDetail = false } = {}) {
  const label = escapeHtml(_stepLabel(step));
  if (step.kind === "say") {
    const text = step.text.length > SAY_MAX ? `${step.text.slice(0, SAY_MAX)}…` : step.text;
    return `<li class="say" title="${escapeHtml(step.text)}">${escapeHtml(text)}</li>`;
  }
  const cls = [step.done ? "" : "now", step.error ? "err" : ""].filter(Boolean).join(" ");
  const clsAttr = cls ? ` class="${cls}"` : "";
  const target = step.target ? ` <code>${escapeHtml(step.target)}</code>` : "";
  if (withDetail && step.result) {
    return `<li${clsAttr}><details class="think-step-detail"><summary>${label}${target}</summary>` +
      `<pre>${escapeHtml(step.result)}</pre></details></li>`;
  }
  return `<li${clsAttr}>${label}${target}</li>`;
}

/**
 * Tools-zone HTML for a streaming bubble: the thinking UI while no reply text
 * exists, nothing once the reply streams.
 */
export function renderThinkZone(msg) {
  if (!isThinking(msg)) return "";
  const think = msg.think;
  const collapsed = _collapsed.has(think.id);
  const elapsed = formatElapsed((Date.now() - think.startedAt) / 1000);
  const steps = think.steps.map(s => _stepHtml(s)).join("");
  _ensureTicker();
  return `<div class="think${collapsed ? " collapsed" : ""}" data-think-id="${escapeHtml(think.id)}" role="button" tabindex="0"` +
    ` aria-expanded="${collapsed ? "false" : "true"}" title="${escapeHtml(t("chat.think.toggle_hint"))}">` +
    `<div class="think-top"><span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>` +
    `<span class="think-now" aria-live="polite">${escapeHtml(currentLabel(msg))}</span>` +
    `<span class="think-time" data-since="${think.startedAt}">${elapsed}</span></div>` +
    `<div class="think-bar" aria-hidden="true"><i></i></div>` +
    `<ul class="steps">${steps}</ul>` +
    `<div class="think-foot"><span>${escapeHtml(t("chat.think.steps", { count: stepCount(think) }))}</span>` +
    `<button type="button" class="think-stop" data-think-stop>${escapeHtml(t("chat.think.stop"))}</button></div>` +
    `</div>`;
}

function _foldHtml(steps, count) {
  return `<details class="think-fold"><summary>${escapeHtml(t("chat.think.steps", { count }))}</summary>` +
    `<ul class="steps">${steps}</ul></details>`;
}

/** Folded "Steps n ▸" list under a finished reply ("" when nothing was done). */
export function renderStepsFold(msg) {
  const think = msg?.think;
  if (!think || !think.steps.some(s => s.kind !== "think")) return "";
  return _foldHtml(think.steps.map(s => _stepHtml(s)).join(""), stepCount(think));
}

/** "Steps n ▸" for a history message, replacing the old Tool Calls group. */
export function renderHistorySteps(toolCalls, { truncateLen = RESULT_MAX } = {}) {
  if (!Array.isArray(toolCalls) || toolCalls.length === 0) return "";
  const html = toolCalls.map(tc => {
    let result = tc.result ?? "";
    if (result && typeof result !== "string") result = JSON.stringify(result, null, 2);
    if (result.length > truncateLen) result = `${result.slice(0, truncateLen)}…`;
    return _stepHtml({
      kind: "tool", tool: tc.tool_name || "", target: _targetFromInput(tc.input),
      done: true, error: !!tc.is_error, result,
    }, { withDetail: true });
  }).join("");
  return _foldHtml(html, toolCalls.length);
}

/**
 * Decorate an avatar for the thinking row: thinking face + pulsing ring while
 * working, the reply's emotion face once done. Missing face assets fall back
 * to the original icon via `data-fallback-src`.
 */
export function thinkAvatar(avatarHtml, msg, animaName) {
  if (!avatarHtml || !msg?.think || !animaName) return avatarHtml;
  const working = isThinking(msg);
  const emotion = msg.streaming ? "thinking" : (msg.emotion || msg.think.emotion || null);
  let html = avatarHtml.replace('class="chat-msg-avatar"',
    `class="chat-msg-avatar think-face${working ? " thinking" : ""}" data-think-id="${escapeHtml(msg.think.id)}"`);
  if (emotion) {
    html = html.replace(/<img class="chat-msg-avatar-img" src="([^"]*)"/, (_m, src) =>
      `<img class="chat-msg-avatar-img" src="${escapeHtml(faceUrl(animaName, emotion))}" data-fallback-src="${src}"`);
  }
  return html;
}

/** Re-sync the avatar ring of an already rendered row (zone renders skip it). */
export function syncThinkAvatar(bubbleEl, msg) {
  const avatar = bubbleEl?.closest?.(".chat-msg-row")?.querySelector(".chat-msg-avatar.think-face");
  if (avatar) avatar.classList.toggle("thinking", isThinking(msg));
}

/** Render hooks handed to render-utils through `opts.think`. */
export const thinkRenderHooks = {
  isThinking,
  zone: renderThinkZone,
  fold: renderStepsFold,
  historyFold: renderHistorySteps,
  avatar: thinkAvatar,
};

// ── DOM: ticker / handlers ──────────────────────

let _tickTimer = null;

function _tick() {
  const els = document.querySelectorAll(".think-time[data-since]");
  if (els.length === 0) {
    clearInterval(_tickTimer);
    _tickTimer = null;
    return;
  }
  const now = Date.now();
  for (const el of els) {
    const text = formatElapsed((now - Number(el.dataset.since)) / 1000);
    if (el.textContent !== text) el.textContent = text;
  }
}

function _ensureTicker() {
  if (_tickTimer || typeof document === "undefined" || typeof setInterval === "undefined") return;
  _tickTimer = setInterval(_tick, TICK_MS);
}

function _toggle(el) {
  const id = el.dataset.thinkId;
  const collapsed = !el.classList.contains("collapsed");
  el.classList.toggle("collapsed", collapsed);
  el.setAttribute("aria-expanded", collapsed ? "false" : "true");
  if (collapsed) _collapsed.add(id); else _collapsed.delete(id);
}

/**
 * Bind delegated handlers on a messages container (idempotent): tap the
 * bubble to open/close the steps, "Stop" to abort the stream.
 */
export function bindThinkingHandlers(container, { onStop } = {}) {
  if (!container || container.dataset.thinkBound) return;
  container.dataset.thinkBound = "1";
  container.addEventListener("click", (e) => {
    if (e.target.closest("[data-think-stop]")) {
      e.preventDefault();
      e.stopPropagation();
      onStop?.();
      return;
    }
    const think = e.target.closest(".think[data-think-id]");
    if (think) _toggle(think);
  });
  container.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const think = e.target.closest?.(".think[data-think-id]");
    if (!think || e.target !== think) return;
    e.preventDefault();
    _toggle(think);
  });
}

if (typeof document !== "undefined" && !globalThis.__awThinkFallbackBound) {
  globalThis.__awThinkFallbackBound = true;
  // Face images may not exist for every Anima; fall back to the plain icon.
  document.addEventListener("error", (e) => {
    const img = e.target;
    if (img?.tagName !== "IMG" || !img.dataset?.fallbackSrc) return;
    const src = img.dataset.fallbackSrc;
    delete img.dataset.fallbackSrc;
    img.src = src;
  }, true);
}
