import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const sourcePath = resolve(__dirname, "../../../server/static/pages/chat/memory-popover.js");
const source = readFileSync(sourcePath, "utf8").replace(/^import .+;\r?\n/gm, "");
const chatPageSource = readFileSync(resolve(__dirname, "../../../server/static/pages/chat.js"), "utf8");

class FakeClassList {
  constructor(owner) {
    this.owner = owner;
  }
  _set() {
    return new Set(String(this.owner._className || "").split(/\s+/).filter(Boolean));
  }
  _write(values) {
    this.owner._className = [...values].join(" ");
  }
  add(...values) {
    const set = this._set();
    values.forEach((value) => set.add(value));
    this._write(set);
  }
  remove(...values) {
    const set = this._set();
    values.forEach((value) => set.delete(value));
    this._write(set);
  }
  contains(value) {
    return this._set().has(value);
  }
  toggle(value, force) {
    const set = this._set();
    const shouldAdd = force === undefined ? !set.has(value) : Boolean(force);
    if (shouldAdd) set.add(value);
    else set.delete(value);
    this._write(set);
    return shouldAdd;
  }
}

const VOID_ELEMENTS = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr", "path", "circle"]);

class FakeElement {
  constructor(tagName, ownerDocument) {
    this.tagName = tagName.toUpperCase();
    this.ownerDocument = ownerDocument;
    this.parentElement = null;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.style = { setProperty(name, value) { this[name] = value; } };
    this.hidden = false;
    this.value = "";
    this._innerHTML = "";
    this._textContent = "";
    this._className = "";
    this.classList = new FakeClassList(this);
    this._listeners = new Map();
  }
  set className(value) {
    this._className = String(value || "");
  }
  get className() {
    return this._className;
  }
  set innerHTML(value) {
    this._innerHTML = String(value ?? "");
    this._textContent = "";
    this.children = [];
    const stack = [this];
    const tokens = this._innerHTML.match(/<\/?[\w-]+(?:\s[^<>]*?)?\s*\/?>/g) || [];
    for (const token of tokens) {
      const closing = token.match(/^<\/([\w-]+)/);
      if (closing) {
        for (let i = stack.length - 1; i > 0; i--) {
          if (stack[i].tagName.toLowerCase() === closing[1].toLowerCase()) {
            stack.length = i;
            break;
          }
        }
        continue;
      }
      const match = token.match(/^<([\w-]+)([\s\S]*?)\/?>$/);
      if (!match) continue;
      const tag = match[1].toLowerCase();
      const element = this.ownerDocument.createElement(tag);
      const attrs = match[2];
      for (const attr of attrs.matchAll(/([:\w-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) {
        const name = attr[1];
        const attrValue = attr[2] ?? attr[3] ?? attr[4] ?? "";
        element.setAttribute(name, attrValue);
      }
      stack.at(-1).appendChild(element);
      if (!VOID_ELEMENTS.has(tag) && !token.endsWith("/>")) stack.push(element);
    }
  }
  get innerHTML() {
    return this._innerHTML;
  }
  set textContent(value) {
    this._textContent = String(value ?? "");
    this.children = [];
  }
  get textContent() {
    return this._textContent + this.children.map((child) => child.textContent).join("");
  }
  get isConnected() {
    let node = this;
    while (node) {
      if (node === this.ownerDocument.body) return true;
      node = node.parentElement;
    }
    return false;
  }
  getBoundingClientRect() {
    return { left: 20, top: 10, width: 40, height: 40, right: 60, bottom: 50 };
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === "class") this.className = value;
    else if (name === "hidden") this.hidden = true;
    else if (name.startsWith("data-")) {
      const key = name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
      this.dataset[key] = String(value);
    }
  }
  getAttribute(name) {
    return this.attributes[name] ?? null;
  }
  appendChild(element) {
    element.parentElement?.removeChild(element);
    element.parentElement = this;
    this.children.push(element);
    if (this.tagName === "HEAD" && element.tagName === "SCRIPT") {
      queueMicrotask(() => element.dispatchEvent({ type: "error" }));
    }
    return element;
  }
  removeChild(element) {
    this.children = this.children.filter((child) => child !== element);
    element.parentElement = null;
  }
  remove() {
    this.parentElement?.removeChild(this);
  }
  addEventListener(type, handler) {
    if (!this._listeners.has(type)) this._listeners.set(type, []);
    this._listeners.get(type).push(handler);
  }
  removeEventListener(type, handler) {
    this._listeners.set(type, (this._listeners.get(type) || []).filter((current) => current !== handler));
  }
  dispatchEvent(event) {
    if (!event.target) event.target = this;
    event.currentTarget = this;
    for (const handler of this._listeners.get(event.type) || []) handler(event);
    if (event.bubbles !== false && this.parentElement) this.parentElement.dispatchEvent(event);
    return true;
  }
  click() {
    this.dispatchEvent({ type: "click", bubbles: true });
  }
  focus() {
    this.ownerDocument.activeElement = this;
  }
  matches(selector) {
    let rest = selector;
    const tag = rest.match(/^[a-z][\w-]*/i)?.[0];
    if (tag && this.tagName.toLowerCase() !== tag.toLowerCase()) return false;
    if (tag) rest = rest.slice(tag.length);
    for (const match of rest.matchAll(/\.([\w-]+)/g)) {
      if (!this.classList.contains(match[1])) return false;
    }
    for (const match of rest.matchAll(/\[([^\]=]+)(?:="([^"]*)")?\]/g)) {
      const key = match[1];
      const dataKey = key.startsWith("data-") ? key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()) : null;
      const value = dataKey ? this.dataset[dataKey] : this.getAttribute(key);
      if (value == null || (match[2] != null && String(value) !== match[2])) return false;
    }
    return true;
  }
  closest(selector) {
    let node = this;
    while (node) {
      if (node.matches?.(selector)) return node;
      node = node.parentElement;
    }
    return null;
  }
  querySelectorAll(selector) {
    const found = [];
    const visit = (node) => {
      for (const child of node.children) {
        if (child.matches(selector)) found.push(child);
        visit(child);
      }
    };
    visit(this);
    return found;
  }
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
}

class FakeDocument {
  constructor() {
    this._listeners = new Map();
    this.body = new FakeElement("body", this);
    this.head = new FakeElement("head", this);
  }
  createElement(tagName) {
    return new FakeElement(tagName, this);
  }
  querySelector() {
    return null;
  }
  getElementById() {
    return null;
  }
  addEventListener(type, handler) {
    if (!this._listeners.has(type)) this._listeners.set(type, []);
    this._listeners.get(type).push(handler);
  }
  removeEventListener(type, handler) {
    this._listeners.set(type, (this._listeners.get(type) || []).filter((current) => current !== handler));
  }
  dispatchEvent(event) {
    event.target = this;
    event.currentTarget = this;
    for (const handler of this._listeners.get(event.type) || []) handler(event);
  }
}

const translations = {
  "chat.memory.tab.graph": "Connections",
  "chat.memory.tab.state": "Current state",
  "chat.memory.tab.files": "Memory files",
  "chat.memory.tab.days": "Diary",
  "chat.memory.tab.activity": "Activity",
  "chat.memory.tab.routine": "Routine",
  "chat.memory.say_empty": "Reviewing memories.",
  "chat.memory.ask_text": "Tell me what you remember about {name}",
  "chat.memory.detail.ask": "Ask {anima} about {name}",
  "chat.memory.detail.fact_count": "{count} facts",
  "chat.memory.detail.last_seen": "Last mentioned {date}",
  "chat.memory.kind.person": "People",
  "chat.memory.files.knowledge": "Knowledge",
  "chat.memory.files.procedures": "Procedures",
  "chat.memory.close": "Close",
};

const apiSource = "const basePath = ''; \n" + source;
const moduleUrl = "data:text/javascript;base64," + Buffer.from(apiSource, "utf8").toString("base64");
const { bubbleRadius, createMemoryPopover, kindColorVar, pickSayLine, splitStateSections, tailLeft } = await import(moduleUrl);

function t(key, params = {}) {
  let value = translations[key] || key;
  for (const [name, replacement] of Object.entries(params)) value = value.replaceAll("{" + name + "}", String(replacement));
  return value;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function makeContext(api, extra = {}) {
  const document = new FakeDocument();
  const window = {
    innerWidth: 1200,
    innerHeight: 900,
    setInterval: () => 1,
    clearInterval: () => {},
  };
  const input = new FakeElement("textarea", document);
  let sends = 0;
  let activityLoads = 0;
  return {
    document,
    window,
    input,
    get sends() { return sends; },
    get activityLoads() { return activityLoads; },
    send() { sends += 1; },
    ctx: {
      document,
      window,
      state: {
        selectedAnima: "mei",
        animaSummary: { role: "Secretary" },
        animas: [{ name: "mei", role: "Secretary" }],
        users: [],
      },
      deps: {
        api,
        t,
        escapeHtml,
        renderMarkdown: (markdown) => "<p>" + escapeHtml(markdown) + "</p>",
      },
      controllers: {
        activity: {
          async loadActivity({ target }) {
            activityLoads += 1;
            target.innerHTML = '<div class="activity-entry">Activity entry</div>';
            return [{ type: "task", summary: "Activity entry" }];
          },
          renderActivity(events, target) {
            target.innerHTML = events.map((item) => '<div class="activity-entry">' + escapeHtml(item.summary) + "</div>").join("");
          },
        },
      },
      $: (id) => id === "chatPageInput" ? input : null,
      $root: () => null,
      ...extra,
    },
  };
}

function apiStub(calls, { nodes = [], files = ["interior-decisions"], episodes = ["2026-10-28"] } = {}) {
  return async (endpoint) => {
    calls.push(endpoint);
    if (endpoint.endsWith("/memory/stats")) {
      return { facts: 1, episodes: { count: 1 }, knowledge: { count: 1 }, procedures: { count: 1 } };
    }
    if (endpoint.endsWith("/state")) {
      return { state: "# Today\n2026-10-29\n- Meeting preparation is underway.\n## Schedule\n10:00 Team meeting" };
    }
    if (endpoint.includes("/memory/connections/entity?")) {
      return {
        entity: "佐藤さん",
        kind: "person",
        count: 3,
        last_seen: "2026-10-28",
        facts: [{ text: "Meeting at the station.", recorded_at: "2026-10-28T08:00:00+09:00" }],
        related: [],
        files: [],
      };
    }
    if (endpoint.includes("/memory/connections?")) return { anima: "mei", nodes, links: [], totals: { facts: 1, entities: nodes.length } };
    if (endpoint.endsWith("/knowledge")) return { files };
    if (endpoint.endsWith("/procedures")) return { files: ["meeting-brief"] };
    if (endpoint.endsWith("/episodes")) return { files: episodes };
    if (endpoint.endsWith("/heartbeat") || endpoint.endsWith("/cron")) return { content: "# Routine\nCheck the schedule." };
    if (endpoint.includes("/knowledge/") || endpoint.includes("/procedures/") || endpoint.includes("/episodes/")) {
      return { content: "---\nupdated_at: 2026-10-28\n---\n# Memory title\nThe first preview line." };
    }
    throw new Error("Unexpected API request: " + endpoint);
  };
}

async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("memory popover helpers", () => {
  it("skips headings and date-only lines and truncates the first meaningful line", () => {
    assert.equal(pickSayLine("# Current state\n\n2026-10-29\n- Meeting preparation is underway."), "Meeting preparation is underway.");
    assert.equal(pickSayLine("> # Current state\n- 2026-10-29\n> - Meeting preparation is underway."), "Meeting preparation is underway.");
    assert.equal([...pickSayLine("x".repeat(80))].length, 60);
  });

  it("uses a square-root scale, five kind colors, and bounded tail positioning", () => {
    assert.equal(bubbleRadius(0, 100), 10);
    assert.ok(bubbleRadius(25, 100) < bubbleRadius(100, 100));
    assert.equal(bubbleRadius(100, 100), 46);
    assert.equal(kindColorVar("user"), "--aw-mem-k-anima");
    assert.equal(kindColorVar("person"), "--aw-mem-k-person");
    assert.equal(kindColorVar("service"), "--aw-mem-k-service");
    assert.equal(kindColorVar("place"), "--aw-mem-k-place");
    assert.equal(kindColorVar("other"), "--aw-mem-k-topic");
    assert.equal(tailLeft({ left: 0, width: 10 }, { left: 0, width: 100 }), 24);
    assert.equal(tailLeft({ left: 200, width: 20 }, { left: 0, width: 100 }), 76);
  });

  it("splits current-state markdown into level-two sections", () => {
    assert.deepEqual(splitStateSections("Summary\n## Today\nMeeting\n## Waiting\nOne item"), [
      { heading: "", body: "Summary" },
      { heading: "Today", body: "Meeting" },
      { heading: "Waiting", body: "One item" },
    ]);
  });
});

describe("memory popover behavior", () => {
  it("removes the fixed right-pane DOM from the chat page", () => {
    const removedElements = [
      ["chat-page", "sidebar"].join("-"),
      ["chatRightPane", "ToggleBtn"].join(""),
      [".chat-memory", "section"].join("-"),
    ];
    assert.equal(removedElements.some((selector) => chatPageSource.includes(selector)), false);
  });

  it("stays closed when no anima is active", () => {
    const harness = makeContext(apiStub([]));
    harness.ctx.state.selectedAnima = null;
    const popover = createMemoryPopover(harness.ctx);

    popover.open(harness.document.createElement("button"));
    assert.equal(popover.isOpen(), false);
    popover.destroy();
  });

  it("loads tab APIs on demand and reuses cached results for the same anima", async () => {
    const calls = [];
    const harness = makeContext(apiStub(calls));
    const popover = createMemoryPopover(harness.ctx);
    const anchor = harness.document.createElement("button");

    popover.open(anchor);
    await settle();
    assert.equal(popover.isOpen(), true);
    assert.equal(calls.filter((call) => call.endsWith("/knowledge")).length, 0);
    assert.equal(calls.filter((call) => call.endsWith("/episodes")).length, 0);
    assert.equal(harness.activityLoads, 0);
    assert.equal(calls.some((call) => call.endsWith("/heartbeat")), false);

    const root = harness.document.body.querySelector(".aw-memory-overlay");
    root.querySelector('[data-memory-tab="files"]').click();
    await settle();
    assert.equal(calls.filter((call) => call.endsWith("/knowledge")).length, 1);
    assert.equal(calls.filter((call) => call.endsWith("/procedures")).length, 1);

    root.querySelector('[data-memory-tab="days"]').click();
    await settle();
    assert.equal(calls.filter((call) => call.endsWith("/episodes")).length, 1);
    root.querySelector('[data-memory-tab="activity"]').click();
    await settle();
    assert.equal(harness.activityLoads, 1);
    root.querySelector('[data-memory-tab="routine"]').click();
    await settle();
    assert.equal(calls.filter((call) => call.endsWith("/heartbeat")).length, 1);
    assert.equal(calls.filter((call) => call.endsWith("/cron")).length, 1);

    root.querySelector('[data-memory-tab="files"]').click();
    await settle();
    assert.equal(calls.filter((call) => call.endsWith("/knowledge")).length, 1);
    assert.equal(calls.filter((call) => call.endsWith("/procedures")).length, 1);
    root.querySelector('[data-memory-tab="days"]').click();
    await settle();
    assert.equal(calls.filter((call) => call.endsWith("/episodes")).length, 1);
    root.querySelector('[data-memory-tab="activity"]').click();
    await settle();
    assert.equal(harness.activityLoads, 1);

    popover.close();
    popover.open(anchor);
    await settle();
    assert.equal(calls.filter((call) => call.endsWith("/knowledge")).length, 1);
    assert.equal(calls.filter((call) => call.endsWith("/memory/connections?limit=40")).length, 2);
    popover.destroy();
  });

  it("loads one entity detail on selection and asks without submitting", async () => {
    const calls = [];
    const harness = makeContext(apiStub(calls, {
      nodes: [{ id: "佐藤さん", label: "佐藤さん", kind: "person", count: 3, last_seen: "2026-10-28" }],
    }));
    const popover = createMemoryPopover(harness.ctx);
    popover.open(harness.document.createElement("button"));
    await settle();
    await settle();

    const root = harness.document.body.querySelector(".aw-memory-overlay");
    const entity = root.querySelector('[data-memory-entity="佐藤さん"]');
    assert.ok(entity, "graph node is available in the D3 fallback list");
    entity.click();
    await settle();
    assert.equal(calls.filter((call) => call.includes("/memory/connections/entity?name=")).length, 1);

    root.querySelector('[data-memory-action="ask"]').click();
    assert.equal(harness.input.value, "Tell me what you remember about 佐藤さん");
    assert.equal(harness.document.activeElement, harness.input);
    assert.equal(harness.sends, 0);
    assert.equal(calls.some((call) => call.includes("/chat/")), false);
    assert.equal(popover.isOpen(), false);
    popover.destroy();
  });

  it("closes from Escape and the backdrop", async () => {
    const calls = [];
    const harness = makeContext(apiStub(calls));
    const popover = createMemoryPopover(harness.ctx);
    const anchor = harness.document.createElement("button");

    popover.open(anchor);
    await settle();
    harness.document.dispatchEvent({ type: "keydown", key: "Escape" });
    assert.equal(popover.isOpen(), false);

    popover.open(anchor);
    await settle();
    harness.document.body.querySelector('[data-memory-action="scrim"]').click();
    assert.equal(popover.isOpen(), false);
    popover.destroy();
  });
});
