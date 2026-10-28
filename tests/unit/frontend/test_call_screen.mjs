/**
 * Call screen behavior tests.
 * Run with: node --test tests/unit/frontend/test_call_screen.mjs
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

const sharedVoiceManager = {
  on() {},
  off() {},
  connect() { return Promise.resolve(); },
  setMode() {},
  disconnect() {},
};
globalThis.__callScreenVoiceManager = sharedVoiceManager;

class FakeClassList {
  constructor(owner) { this.owner = owner; }
  _items() { return new Set(this.owner._className.split(/\s+/).filter(Boolean)); }
  add(...names) { const set = this._items(); names.forEach(name => set.add(name)); this.owner._className = [...set].join(" "); }
  remove(...names) { const set = this._items(); names.forEach(name => set.delete(name)); this.owner._className = [...set].join(" "); }
  contains(name) { return this._items().has(name); }
  toggle(name, force) {
    const present = this.contains(name);
    const shouldAdd = force === undefined ? !present : Boolean(force);
    if (shouldAdd) this.add(name); else this.remove(name);
    return shouldAdd;
  }
}

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this._className = "";
    this.classList = new FakeClassList(this);
    this.children = [];
    this.parentNode = null;
    this.parentElement = null;
    this.attributes = {};
    this.listeners = new Map();
    this.hidden = false;
    this.style = {};
    this.dataset = {};
    this._textContent = "";
    this._src = "";
  }
  set className(value) { this._className = String(value || ""); }
  get className() { return this._className; }
  set textContent(value) {
    this._textContent = String(value ?? "");
    this.children.forEach(child => { child.parentNode = null; child.parentElement = null; });
    this.children = [];
  }
  get textContent() { return this._textContent + this.children.map(child => child.textContent).join(""); }
  set src(value) {
    this._src = String(value);
    queueMicrotask(() => {
      if (this._src.includes("_frame_")) this.onerror?.();
      else this.onload?.();
    });
  }
  get src() { return this._src; }
  set innerHTML(value) { this._innerHTML = String(value); }
  get innerHTML() { return this._innerHTML || ""; }
  appendChild(child) {
    if (child.parentNode) child.parentNode.removeChild(child);
    child.parentNode = this;
    child.parentElement = this;
    this.children.push(child);
    return child;
  }
  removeChild(child) {
    this.children = this.children.filter(item => item !== child);
    child.parentNode = null;
    child.parentElement = null;
    return child;
  }
  remove() { this.parentNode?.removeChild(this); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; if (name === "src") this._src = ""; }
  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(handler);
  }
  removeEventListener(type, handler) {
    this.listeners.set(type, (this.listeners.get(type) || []).filter(item => item !== handler));
  }
  dispatch(type, event = {}) {
    for (const handler of this.listeners.get(type) || []) handler({ target: this, preventDefault() {}, stopPropagation() {}, ...event });
  }
  querySelector(selector) {
    const className = selector.startsWith(".") ? selector.slice(1) : null;
    if (!className) return null;
    const visit = (node) => {
      for (const child of node.children) {
        if (child.classList.contains(className)) return child;
        const nested = visit(child);
        if (nested) return nested;
      }
      return null;
    };
    return visit(this);
  }
}

function installFakeDocument() {
  const listeners = new Map();
  const dispatched = [];
  const body = new FakeElement("body");
  const doc = {
    body,
    createElement: tag => new FakeElement(tag),
    querySelector: () => null,
    addEventListener(type, handler) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(handler);
    },
    removeEventListener(type, handler) {
      listeners.set(type, (listeners.get(type) || []).filter(item => item !== handler));
    },
    dispatchEvent(event) {
      dispatched.push(event);
      for (const handler of listeners.get(event.type) || []) handler(event);
      return true;
    },
  };
  return { doc, body, listeners, dispatched };
}

const callSource = readFileSync(resolve(__dirname, "../../../server/static/pages/chat/call-screen.js"), "utf8")
  .replace(/^import \{ voiceManager \} from .*;$/m, "const voiceManager = globalThis.__callScreenVoiceManager;")
  .replace(/^import \{ destroyVoiceUI \} from .*;$/m, "const destroyVoiceUI = () => {}; ")
  .replace(/^import \{ BustupAnimator \} from .*;$/m, "class BustupAnimator { constructor() {} setExpression() {} startLipsync() {} stopLipsync() {} destroy() {} }")
  .replace(/^import \{ api \} from .*;$/m, "const api = async () => ({});")
  .replace(/^import \{ bustupCandidates, resolveCachedAvatar \} from .*;$/m, "const bustupCandidates = () => []; const resolveCachedAvatar = async () => null;")
  .replace(/^import \{ t \} from .*;$/m, "const t = (key, params = {}) => Object.entries(params).reduce((s, [k, v]) => s.replaceAll(`{${k}}`, v), key);");
const callModuleUrl = "data:text/javascript;base64," + Buffer.from(callSource, "utf8").toString("base64");
const { CallScreen, formatElapsedTime } = await import(callModuleUrl);

const renderUtilsSource = readFileSync(resolve(__dirname, "../../../server/static/shared/chat/render-utils.js"), "utf8")
  .replace(/^import \{ t \} from .*;$/m, 'const t = (key, params = {}) => key === "chat.call.record_duration" ? `Call ${params.time}` : key === "chat.call.open_transcript" ? "Open transcript" : key === "chat.call.you" ? "You" : key;')
  .replace(/^import \{ escapeAttr as _escapeAttr \} from .*;$/m, "const _escapeAttr = value => String(value);")
  .replace(/^import \{ api \} from .*;$/m, "const api = async () => ({});")
  .replace(/^import \{ bustUrl, faceUrl \} from .*;$/m, "const bustUrl = () => \"\"; const faceUrl = () => \"\";");
const renderUtilsUrl = "data:text/javascript;base64," + Buffer.from(renderUtilsSource, "utf8").toString("base64");
const { renderHistoryMessage } = await import(renderUtilsUrl);

class MockVoiceManager {
  constructor() { this.events = new Map(); this.modes = []; this.disconnectCount = 0; }
  on(event, handler) {
    if (!this.events.has(event)) this.events.set(event, []);
    this.events.get(event).push(handler);
  }
  off(event, handler) { this.events.set(event, (this.events.get(event) || []).filter(item => item !== handler)); }
  emit(event, data) { for (const handler of this.events.get(event) || []) handler(data); }
  connect(name) { this.name = name; return Promise.resolve(); }
  setMode(mode) { this.modes.push(mode); }
  stopRecording() { this.stopped = true; }
  disconnect() { this.disconnectCount += 1; }
  get ttsRMS() { return 0.4; }
}

function makeOptions(overrides = {}) {
  const { doc, body, dispatched } = installFakeDocument();
  let now = Date.UTC(2026, 9, 28, 3, 0, 0);
  const intervals = new Map();
  let nextTimer = 0;
  const posted = [];
  const voice = new MockVoiceManager();
  const container = new FakeElement("main");
  const animatorCalls = [];
  const animatorFactory = () => {
    const animator = {
      expressions: [],
      setExpression(expression) { this.expressions.push(expression); },
      startLipsync(getRMS) { this.getRMS = getRMS; },
      stopLipsync() { this.getRMS = null; },
      destroy() { this.destroyed = true; },
    };
    animatorCalls.push(animator);
    return animator;
  };
  Object.assign(globalThis, {
    document: doc,
    CustomEvent: class CustomEvent { constructor(type, init = {}) { this.type = type; this.detail = init.detail; } },
  });
  return {
    doc, body, dispatched, container, voice, animatorCalls, posted,
    opts: {
      container,
      voice,
      animatorFactory,
      removeVoiceUI() {},
      now: () => now,
      setInterval(fn) { const id = ++nextTimer; intervals.set(id, fn); return id; },
      clearInterval(id) { intervals.delete(id); },
      setTimeout(fn) { const id = ++nextTimer; intervals.set(id, fn); return id; },
      clearTimeout(id) { intervals.delete(id); },
      postCall: async (name, record) => { posted.push({ name, record }); },
      ...overrides,
    },
    setNow(value) { now = value; },
  };
}

describe("call screen", () => {
  it("uses the shared voice manager unless a test or caller injects one", () => {
    const setup = makeOptions();
    const screen = new CallScreen("mei", setup.container, { ...setup.opts, voice: undefined });
    assert.equal(screen.voice, sharedVoiceManager);
    assert.notEqual(screen.voice, setup.voice);
  });

  it("switches from ringing to connected and formats elapsed time", async () => {
    const setup = makeOptions();
    const screen = new CallScreen("mei", setup.container, setup.opts);
    screen.start();
    await Promise.resolve();

    assert.equal(screen.els.root.classList.contains("is-ringing"), true);
    assert.equal(screen.els.ring.hidden, false);
    setup.voice.emit("connected");
    assert.equal(screen.els.root.classList.contains("is-connected"), true);
    assert.equal(screen.els.ring.hidden, true);
    assert.equal(screen.els.self.hidden, false);
    assert.equal(screen.els.time.textContent, "0:00");
    assert.equal(formatElapsedTime(0), "0:00");
    assert.equal(formatElapsedTime(61.9), "1:01");
    assert.equal(formatElapsedTime(3600), "60:00");
    await screen.finish();
  });

  it("moves between full screen and PiP without disconnecting the call", () => {
    const setup = makeOptions();
    const screen = new CallScreen("mei", setup.container, setup.opts);
    screen.start();
    screen.openTranscript();
    assert.equal(screen.els.transcriptDialog.hidden, false);
    setup.doc.dispatchEvent({ type: "keydown", key: "Escape", preventDefault() {} });
    assert.equal(screen.els.root.hidden, true);
    assert.equal(screen.els.pip.hidden, false);
    assert.equal(screen.els.transcriptDialog.hidden, true);
    assert.equal(setup.voice.disconnectCount, 0);
    screen.els.pip.dispatch("click");
    assert.equal(screen.els.root.hidden, false);
    assert.equal(screen.els.pip.hidden, true);
    screen.toggleMute();
    assert.equal(setup.voice.stopped, true);
    assert.equal(setup.voice.modes.at(-1), "ptt");
    screen.toggleMute();
    assert.equal(setup.voice.modes.at(-1), "vad");
    screen.toggleCaptions();
    assert.equal(screen.els.root.classList.contains("captions-hidden"), true);
    void screen.finish();
  });

  it("persists duration, summary, and transcript when ended", async () => {
    const setup = makeOptions();
    const screen = new CallScreen("mei", setup.container, setup.opts);
    screen.start();
    assert.equal(setup.dispatched[0].detail.phase, "call-start");
    setup.voice.emit("connected");
    setup.voice.emit("transcript", { text: "証明書の状態はどう？" });
    setup.voice.emit("responseStart");
    setup.voice.emit("responseText", { text: "証明書を確認しました。" });
    setup.voice.emit("responseDone", { emotion: "smile" });
    setup.setNow(Date.UTC(2026, 9, 28, 3, 1, 24));

    const record = await screen.finish();
    assert.equal(setup.dispatched.at(-1).detail.phase, "call-end");
    assert.equal(record.duration_seconds, 84);
    assert.equal(record.summary, "証明書を確認しました。");
    assert.deepEqual(record.transcript, [
      { speaker: "user", text: "証明書の状態はどう？" },
      { speaker: "assistant", text: "証明書を確認しました。" },
    ]);
    assert.equal(setup.posted.length, 1);
    assert.equal(setup.voice.disconnectCount, 1);
    assert.equal(setup.animatorCalls.every(animator => animator.destroyed), true);
  });

  it("renders the saved call record with its transcript disclosure", () => {
    const html = renderHistoryMessage({
      role: "assistant",
      type: "voice_call",
      ts: "2026-10-28T03:01:24+00:00",
      content: "証明書の設定を確認しました。",
      duration_seconds: 84,
      transcript: [{ speaker: "user", text: "証明書の状態はどう？" }],
    }, {
      animaName: "mei",
      escapeHtml: value => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;"),
      renderMarkdown: () => "",
      smartTimestamp: () => "12:01",
    });
    assert.match(html, /chat-call-record/);
    assert.match(html, /Call 1:24/);
    assert.match(html, /証明書の設定を確認しました/);
    assert.match(html, /Open transcript/);
    assert.match(html, /証明書の状態はどう/);
  });

  it("uses the existing animator's static bustup when frame files are absent", async () => {
    const sourcePath = resolve(__dirname, "../../../server/static/pages/chat/bustup-animator.js");
    const animatorSource = readFileSync(sourcePath, "utf8")
      .replace(/^import \{ api \} from .*;$/m, "const api = async () => ({ ok: false });")
      .replace(/^import\s*\{[^}]*\}\s*from\s*"\.\.\/\.\.\/modules\/avatar-resolver\.js";?\s*$/m,
        'const assetUrl = (name, file) => `/assets/${name}/${file}`; const bustupExpressionCandidates = (expr) => [expr === "neutral" ? "avatar_bustup.png" : `avatar_bustup_${expr}.png`]; const isRealisticMode = () => false;');
    const animatorUrl = "data:text/javascript;base64," + Buffer.from(animatorSource, "utf8").toString("base64");
    const { BustupAnimator } = await import(animatorUrl);

    const oldDocument = globalThis.document;
    const oldWindow = globalThis.window;
    const oldRaf = globalThis.requestAnimationFrame;
    const oldCancelRaf = globalThis.cancelAnimationFrame;
    const { doc } = installFakeDocument();
    globalThis.document = doc;
    globalThis.window = {
      matchMedia: () => ({ matches: false }),
      addEventListener() {},
      removeEventListener() {},
      innerWidth: 800,
      innerHeight: 600,
    };
    globalThis.requestAnimationFrame = () => 1;
    globalThis.cancelAnimationFrame = () => {};
    const container = new FakeElement("div");
    const animator = new BustupAnimator(container, "mei");
    await animator.setExpression("neutral");

    assert.equal(animator._mode, "static");
    assert.equal(animator._currentLayer.fallback.src, "/assets/mei/avatar_bustup.png");
    animator.destroy();
    globalThis.document = oldDocument;
    globalThis.window = oldWindow;
    globalThis.requestAnimationFrame = oldRaf;
    globalThis.cancelAnimationFrame = oldCancelRaf;
  });

  it("does not bind a long-press popup while keeping the tab click handler", () => {
    const source = readFileSync(resolve(__dirname, "../../../server/static/pages/chat/anima-controller.js"), "utf8");
    assert.doesNotMatch(source, /openVoicePopup|_bindAnimaLongPress/);
    assert.match(source, /_suppressLongPressClick\(btn\)/);
    assert.match(source, /btn\.addEventListener\("click"/);
  });
});
