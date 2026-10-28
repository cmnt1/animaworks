/**
 * Anima presence store — single source of "who is doing what" for the chat UI.
 *
 * Consumers (left rail, pane header, presence panel, toasts) subscribe here
 * instead of polling individually. This module is dependency-free so it can be
 * unit-tested under node; browser wiring lives in {@link initPresence}.
 *
 * Entry shape: { working, calling, awaitingHuman, unread, lastEmotion,
 *                lastEmotionAt, label }
 */

export const EMOTIONS = Object.freeze([
  "neutral", "smile", "laugh", "troubled", "surprised", "thinking", "embarrassed",
]);

/** lastEmotion stays authoritative for this long after a reply (rail / header). */
export const EMOTION_TTL_MS = 10 * 60 * 1000;
/** Presence panel reverts to the neutral face this long after a reply. */
export const PANEL_EMOTION_TTL_MS = 8000;

const WORK_SOURCES = ["stream", "bg", "status"];

function _blank() {
  return {
    working: false,
    calling: false,
    awaitingHuman: false,
    unread: 0,
    lastEmotion: null,
    lastEmotionAt: 0,
    label: "",
    _src: { stream: false, bg: false, status: false },
  };
}

/** Public, immutable-looking snapshot of an entry. */
function _snapshot(e) {
  return {
    working: e.working,
    calling: e.calling,
    awaitingHuman: e.awaitingHuman,
    unread: e.unread,
    lastEmotion: e.lastEmotion,
    lastEmotionAt: e.lastEmotionAt,
    label: e.label,
  };
}

/**
 * Face to show for an entry.
 * awaiting -> troubled; working/calling -> thinking;
 * recent reply emotion -> that emotion; otherwise neutral.
 */
export function displayEmotion(entry, now = Date.now(), ttlMs = EMOTION_TTL_MS) {
  if (!entry) return "neutral";
  if (entry.awaitingHuman) return "troubled";
  if (entry.working || entry.calling) return "thinking";
  if (
    entry.lastEmotion
    && EMOTIONS.includes(entry.lastEmotion)
    && now - (entry.lastEmotionAt || 0) <= ttlMs
  ) {
    return entry.lastEmotion;
  }
  return "neutral";
}

/** Status kind for labels: "waiting" | "calling" | "working" | "idle". */
export function displayStatus(entry) {
  if (!entry) return "idle";
  if (entry.awaitingHuman) return "waiting";
  if (entry.calling) return "calling";
  if (entry.working) return "working";
  return "idle";
}

export function createPresenceStore({ now = () => Date.now() } = {}) {
  /** @type {Map<string, ReturnType<typeof _blank>>} */
  const entries = new Map();
  const listeners = new Set();
  /** Animas whose conversation is currently on screen (set by the pane host). */
  let visible = new Set();
  let pendingOpen = null;

  function _entry(name) {
    let e = entries.get(name);
    if (!e) { e = _blank(); entries.set(name, e); }
    return e;
  }

  function _notify() {
    for (const fn of [...listeners]) {
      try { fn(); } catch { /* subscriber errors must not break the store */ }
    }
  }

  function _recomputeWorking(e) {
    e.working = WORK_SOURCES.some((k) => e._src[k]);
  }

  /** Apply a mutation; notify only when the public snapshot changed. */
  function _mutate(name, fn) {
    if (!name) return false;
    const e = _entry(name);
    const before = JSON.stringify(_snapshot(e));
    fn(e);
    _recomputeWorking(e);
    if (JSON.stringify(_snapshot(e)) === before) return false;
    _notify();
    return true;
  }

  const api = {
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },

    get(name) {
      return _snapshot(entries.get(name) || _blank());
    },

    names() { return [...entries.keys()]; },

    /** Face for `name` right now. */
    emotionFor(name, ttlMs = EMOTION_TTL_MS) {
      return displayEmotion(entries.get(name), now(), ttlMs);
    },

    statusFor(name) {
      return displayStatus(entries.get(name));
    },

    /** source: "stream" | "bg" | "status" */
    setWorking(name, on, source = "stream", label) {
      return _mutate(name, (e) => {
        e._src[source] = Boolean(on);
        if (on && label) e.label = label;
        // A finished chat stream must not leave its last step ("writing the reply…") behind.
        if (!on && (source === "stream" || !WORK_SOURCES.some((k) => e._src[k]))) e.label = "";
      });
    },

    setLabel(name, label) {
      return _mutate(name, (e) => { e.label = label || ""; });
    },

    setCalling(name, on) {
      return _mutate(name, (e) => { e.calling = Boolean(on); });
    },

    setAwaiting(name, on) {
      return _mutate(name, (e) => { e.awaitingHuman = Boolean(on); });
    },

    setUnread(name, n) {
      const v = Math.max(0, Number(n) || 0);
      return _mutate(name, (e) => { e.unread = v; });
    },

    addUnread(name, n = 1) {
      return _mutate(name, (e) => { e.unread = Math.max(0, e.unread + n); });
    },

    clearUnread(name) {
      return api.setUnread(name, 0);
    },

    setEmotion(name, emotion, at = now()) {
      if (!emotion || !EMOTIONS.includes(emotion)) return false;
      return _mutate(name, (e) => { e.lastEmotion = emotion; e.lastEmotionAt = at; });
    },

    /**
     * Replace the "bg" working source from a poll result: `names` is the set
     * of animas that are busy right now (running tasks / busy lane).
     */
    applyBusySet(names) {
      const busy = new Set(names || []);
      let changed = false;
      for (const n of new Set([...entries.keys(), ...busy])) {
        if (api.setWorking(n, busy.has(n), "bg")) changed = true;
      }
      return changed;
    },

    /**
     * Handle the shared `aw:anima-activity` event detail.
     * detail = { anima, phase, label, emotion, threadId }
     */
    applyActivity(detail) {
      const name = detail?.anima;
      if (!name) return false;
      switch (detail.phase) {
        case "thinking":
        case "tool":
        case "writing":
          // A chat stream means the human just replied, so any pending request is answered.
          return [
            api.setWorking(name, true, "stream", detail.label || ""),
            api.setAwaiting(name, false),
          ].some(Boolean);
        case "done": {
          const a = api.setWorking(name, false, "stream");
          const b = detail.emotion ? api.setEmotion(name, detail.emotion) : false;
          return a || b;
        }
        case "error":
          return api.setWorking(name, false, "stream");
        case "call-start":
          return api.setCalling(name, true);
        case "call-end":
          return api.setCalling(name, false);
        default:
          return false;
      }
    },

    setVisibleAnimas(names) {
      visible = new Set((names || []).filter(Boolean));
    },

    isVisible(name) { return visible.has(name); },
    visibleSet() { return new Set(visible); },

    requestOpen(name) { pendingOpen = name || null; },
    takePendingOpen() {
      const v = pendingOpen;
      pendingOpen = null;
      return v;
    },
  };
  return api;
}

/** Shared singleton used by the UI. */
export const presence = createPresenceStore();

export const subscribe = (fn) => presence.subscribe(fn);
export const get = (name) => presence.get(name);

let _inited = false;
let _timer = null;
const POLL_MS = 15000;

/**
 * Wire the singleton to its information sources. `deps` are injected so the
 * module stays testable: { api, onEvent, doc }.
 */
export function initPresence({ api: apiFn, onEvent, doc = globalThis.document } = {}) {
  if (_inited) return () => {};
  _inited = true;
  const offs = [];

  if (doc?.addEventListener) {
    const h = (ev) => presence.applyActivity(ev.detail);
    doc.addEventListener("aw:anima-activity", h);
    offs.push(() => doc.removeEventListener("aw:anima-activity", h));
  }

  if (onEvent) {
    offs.push(onEvent("anima.status", (d) => {
      const name = d?.name || d?.anima;
      if (!name) return;
      const s = String(d.status || "");
      presence.setWorking(name, s === "busy" || s === "running_task", "status", d.active_label || "");
    }));
    offs.push(onEvent("anima.notification", (d) => {
      const name = d?.anima || d?.name;
      if (name) presence.setAwaiting(name, true);
    }));
    offs.push(onEvent("anima.proactive_message", (d) => {
      const name = d?.anima || d?.name;
      if (name) presence.setAwaiting(name, true);
    }));
    offs.push(onEvent("anima.tool_activity", (d) => {
      const name = d?.name;
      const ev = d?.event || d?.type || "";
      if (name && ev === "tool_start") {
        presence.setWorking(name, true, "bg", d.summary || d.detail || "");
      }
    }));
  }

  async function poll() {
    if (!apiFn) return;
    try {
      const data = await apiFn("/api/activity/running-tasks");
      const busy = new Set();
      for (const a of data?.animas || []) {
        if ((a.tasks && a.tasks.length) || (a.activities && a.activities.length)) busy.add(a.name);
      }
      presence.applyBusySet(busy);
    } catch { /* transient; next tick retries */ }
  }
  poll();
  _timer = setInterval(poll, POLL_MS);
  offs.push(() => { clearInterval(_timer); _timer = null; _inited = false; });

  return () => { for (const off of offs) off(); };
}
