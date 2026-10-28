import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const STATIC = resolve(__dirname, "../../../server/static");
const translations = {
  "chat.think.steps": "Steps {count}",
  "chat.think.loading": "Loading…",
  "chat.think.load_failed": "Could not load",
};
globalThis.__lazyToolTestTranslations = translations;
globalThis.__lazyToolApi = async () => ({ tool_calls: [] });

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[ch]);
const tStub = `const t = (key, params = {}) => {
  let value = globalThis.__lazyToolTestTranslations[key] || key;
  for (const [name, replacement] of Object.entries(params)) value = value.replaceAll("{" + name + "}", replacement);
  return value;
};`;

let thinkSource = readFileSync(resolve(STATIC, "shared/chat/thinking-bubble.js"), "utf8");
thinkSource = thinkSource
  .replace(/^import\s+\{\s*t\s*\}\s+from\s+["'][^"']+["'];?\s*$/m, tStub)
  .replace(/^import\s+\{\s*escapeHtml\s*\}\s+from\s+["'][^"']+["'];?\s*$/m, `const escapeHtml = ${escapeHtml.toString()};`)
  .replace(/^import\s+\{\s*faceUrl\s*\}\s+from\s+["'][^"']+["'];?\s*$/m, "const faceUrl = () => \"\";");
const thinkUrl = "data:text/javascript;base64," + Buffer.from(thinkSource).toString("base64");
const { renderHistorySteps } = await import(thinkUrl);

let renderUtilsSource = readFileSync(resolve(STATIC, "shared/chat/render-utils.js"), "utf8")
  .replace(/^import .*;\r?\n/gm, "");
const renderUtilsPrelude = `${tStub}
  const _escapeAttr = ${escapeHtml.toString()};
  const api = (...args) => globalThis.__lazyToolApi(...args);
  const bustUrl = () => "";
  const faceUrl = () => "";
`;
const renderUtilsUrl = "data:text/javascript;base64," + Buffer.from(renderUtilsPrelude + renderUtilsSource).toString("base64");
const { bindToolCallHandlers, renderHistoryMessage } = await import(renderUtilsUrl);

class FakeDetails {
  constructor(className, dataset = {}, contents = []) {
    this.classNames = new Set(className.split(" "));
    this.classList = { contains: (name) => this.classNames.has(name) };
    this.dataset = dataset;
    this.contents = contents;
    this.listeners = {};
    this.open = false;
  }

  addEventListener(name, callback) {
    (this.listeners[name] ||= []).push(callback);
  }

  querySelectorAll(selector) {
    return selector === "[data-tool-detail-content]" ? this.contents : [];
  }

  closest(selector) {
    return selector === ".think-fold[data-lazy-tool-calls]" ? this.parentFold || null : null;
  }

  toggleOpen() {
    this.open = true;
    for (const callback of this.listeners.toggle || []) callback({ target: this });
  }
}

function bindLazyMessage({ messageTs, threadId = "default", toolUseId = "tool-1" }) {
  const content = { dataset: { toolUseId, toolIndex: "0" }, textContent: "Loading…" };
  const fold = new FakeDetails("think-fold", {
    messageTs,
    anima: "rin",
    threadId,
  }, [content]);
  fold.dataset.lazyToolCalls = "true";
  const step = new FakeDetails("think-step-detail", {});
  step.parentFold = fold;
  const nodes = {
    ".think-fold[data-lazy-tool-calls]": [fold],
    ".think-step-detail[data-lazy-tool-call]": [step],
    ".tool-call-group-header": [],
    ".tool-call-row": [],
    ".tool-call-show-more": [],
  };
  bindToolCallHandlers({ querySelectorAll: (selector) => nodes[selector] || [] });
  return { fold, step, content };
}

describe("lazy tool-call history details", () => {
  it("uses the summary target and marks lazy steps for loading", () => {
    const html = renderHistorySteps([
      { tool_name: "Read", tool_use_id: "tool-1", target: "knowledge/notes.md" },
    ], {
      lazy: true,
      messageTs: "2026-10-28T09:00:00+09:00",
      animaName: "rin",
      threadId: "research",
    });

    assert.match(html, /<code>knowledge\/notes\.md<\/code>/);
    assert.match(html, /data-lazy-tool-calls="true"/);
    assert.match(html, /data-message-ts="2026-10-28T09:00:00\+09:00"/);
    assert.match(html, /data-anima="rin" data-thread-id="research"/);
    assert.match(html, /data-tool-use-id="tool-1"/);
    assert.match(html, /Loading…/);
  });

  it("passes lazy message metadata into the rendered history step list", () => {
    const html = renderHistoryMessage({
      role: "assistant",
      content: "Done",
      ts: "2026-10-28T09:00:00+09:00",
      tool_calls_detail: "lazy",
      tool_calls: [{ tool_name: "Read", tool_use_id: "tool-1", target: "notes.md" }],
    }, {
      lineChat: true,
      animaName: "rin",
      threadId: "research",
      escapeHtml,
      renderMarkdown: (value) => value,
      smartTimestamp: () => "",
      knownAnimaNames: new Set(["rin"]),
      knownUserNames: new Set(["human"]),
      currentUserNames: new Set(["human"]),
      think: { historyFold: renderHistorySteps },
    });

    assert.match(html, /data-lazy-tool-calls="true"/);
    assert.match(html, /data-message-ts="2026-10-28T09:00:00\+09:00"/);
    assert.match(html, /data-anima="rin" data-thread-id="research"/);
  });

  it("loads details when a list or step opens and caches one request per message", async () => {
    const apiCalls = [];
    globalThis.__lazyToolApi = async (url) => {
      apiCalls.push(url);
      return { tool_calls: [{ tool_use_id: "tool-1", result: "full tool result", is_error: false }] };
    };
    const { fold, step, content } = bindLazyMessage({ messageTs: "2026-10-28T09:01:00+09:00", threadId: "research" });

    fold.toggleOpen();
    step.toggleOpen();
    await new Promise((resolvePromise) => setImmediate(resolvePromise));

    assert.equal(apiCalls.length, 1);
    assert.match(apiCalls[0], /\/api\/animas\/rin\/conversation\/tool-calls\?/);
    assert.match(apiCalls[0], /thread_id=research/);
    assert.equal(content.textContent, "full tool result");
  });

  it("shows the translated failure text when the details request fails", async () => {
    globalThis.__lazyToolApi = async () => { throw new Error("unavailable"); };
    const { fold, content } = bindLazyMessage({ messageTs: "2026-10-28T09:02:00+09:00" });

    fold.toggleOpen();
    await new Promise((resolvePromise) => setImmediate(resolvePromise));

    assert.equal(content.textContent, "Could not load");
  });

  it("loads when an individual step opens", async () => {
    const apiCalls = [];
    globalThis.__lazyToolApi = async (url) => {
      apiCalls.push(url);
      return { tool_calls: [{ tool_use_id: "tool-1", result: "step result" }] };
    };
    const { step, content } = bindLazyMessage({ messageTs: "2026-10-28T09:03:00+09:00" });

    step.toggleOpen();
    await new Promise((resolvePromise) => setImmediate(resolvePromise));

    assert.equal(apiCalls.length, 1);
    assert.equal(content.textContent, "step result");
  });
});
