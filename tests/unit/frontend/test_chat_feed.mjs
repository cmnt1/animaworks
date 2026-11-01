import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const staticRoot = resolve(__dirname, "../../../server/static");
const translations = {
  "chat.feed.background_count": "{label} · {count} items",
  "chat.feed.dm": "{people} exchange",
  "chat.feed.failed": "Could not load",
  "chat.feed.hidden_count": "{count} background items hidden",
  "chat.feed.kind.cron": "Scheduled work",
  "chat.feed.kind.dm": "Anima exchange",
  "chat.feed.kind.heartbeat": "Heartbeat",
  "chat.feed.kind.notice": "Notices",
  "chat.feed.kind.other": "Background work",
  "chat.feed.kind.task": "Task execution",
  "chat.feed.loading": "Loading…",
  "chat.feed.people_separator": " and ",
};

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[ch]);
const prelude = `
const t = (key, params = {}) => {
  let value = globalThis.__feedTranslations[key] || key;
  for (const [name, replacement] of Object.entries(params)) value = value.replaceAll("{" + name + "}", replacement);
  return value;
};
const _escapeAttr = ${escapeHtml.toString()};
const api = (...args) => globalThis.__feedApi(...args);
const bustUrl = () => "";
const faceUrl = () => "";
`;
globalThis.__feedTranslations = translations;
globalThis.__feedApi = async () => ({ sessions: [] });

let renderUtilsSource = readFileSync(resolve(staticRoot, "shared/chat/render-utils.js"), "utf8")
  .replace(/^import .*;\r?\n/gm, "");
const moduleUrl = "data:text/javascript;base64," + Buffer.from(prelude + renderUtilsSource).toString("base64");
const {
  bindLazyBackgroundGroups,
  feedBackgroundUrl,
  renderFeedBackgroundGroup,
  renderFeedHiddenCount,
} = await import(moduleUrl);
const historySource = readFileSync(resolve(staticRoot, "shared/chat/history-loader.js"), "utf8");
const historyUrl = "data:text/javascript;base64," + Buffer.from(historySource).toString("base64");
const { applyHistoryData, createHistoryState, mergePolledHistory } = await import(historyUrl);

class FakeBody {
  textContent = "";
  innerHTML = "";
}

class FakeToggle {
  listeners = [];
  addEventListener(name, callback) {
    if (name === "click") this.listeners.push(callback);
  }
  click() {
    for (const callback of this.listeners) callback();
  }
}

class FakeGroup {
  dataset = { fromTs: "from", toTs: "to", anima: "mei", threadId: "default" };
  body = new FakeBody();
  toggle = new FakeToggle();
  querySelector(selector) {
    if (selector === "[data-bg-toggle]") return this.toggle;
    if (selector === ".bg-feed-body") return this.body;
    return null;
  }
}

describe("chat feed rendering", () => {
  it("renders a compact background line with kind, participants, count, and time", () => {
    const html = renderFeedBackgroundGroup({
      from_ts: "2026-10-28T20:00:00+09:00",
      to_ts: "2026-10-28T22:10:00+09:00",
      count: 47,
      kinds: { dm: 47 },
      participants: ["rin"],
      label_hint: "dm",
    }, {
      animaName: "mei",
      threadId: "default",
      escapeHtml,
      smartTimestamp: (value) => value.slice(11, 16),
    });

    assert.match(html, /mei and rin exchange · 47 items/);
    assert.match(html, /20:00 \u301C 22:10/);
    assert.match(html, /data-bg-feed/);
    assert.match(html, /class="chat-sysline-body bg-session-body bg-feed-body" hidden><\/div>/);
  });

  it("loads an expanded background group once and displays a cached render", async () => {
    const group = new FakeGroup();
    let loadCount = 0;
    const urls = [];
    globalThis.__feedApi = async (url) => {
      urls.push(url);
      return { sessions: [] };
    };
    const container = { querySelectorAll: (selector) => selector === "[data-bg-feed]" ? [group] : [] };
    const options = {
      load: async (dataset) => {
        loadCount += 1;
        return globalThis.__feedApi(feedBackgroundUrl(dataset));
      },
      render: () => "expanded background content",
      loadingText: "Loading…",
      failedText: "Could not load",
    };

    bindLazyBackgroundGroups(container, options);
    bindLazyBackgroundGroups(container, options);
    group.toggle.click();
    group.toggle.click();
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

    assert.equal(loadCount, 1);
    assert.equal(urls.length, 1);
    assert.match(urls[0], /\/conversation\/bg\?/);
    assert.equal(group.body.innerHTML, "expanded background content");
    assert.equal(group.dataset.feedLoaded, "1");
  });

  it("targets the background endpoint with the selected thread range", () => {
    assert.equal(
      feedBackgroundUrl({
        anima: "mei",
        threadId: "research",
        fromTs: "2026-10-28T20:00:00+09:00",
        toTs: "2026-10-28T22:10:00+09:00",
      }),
      "/api/animas/mei/conversation/bg?thread_id=research&from_ts=2026-10-28T20%3A00%3A00%2B09%3A00&to_ts=2026-10-28T22%3A10%3A00%2B09%3A00&strict_thread=1",
    );
  });

  it("shows the summed hidden background item count", () => {
    assert.equal(
      renderFeedHiddenCount(47),
      '<div class="chat-bg-hidden-note">47 background items hidden</div>',
    );
    assert.equal(renderFeedHiddenCount(0), "");
  });

  it("provides the new feed labels in every supported locale", () => {
    for (const locale of ["ja", "en", "ko"]) {
      const data = JSON.parse(readFileSync(resolve(staticRoot, `i18n/${locale}.json`), "utf8"));
      assert.ok(data["chat.feed.background_count"]);
      assert.ok(data["chat.feed.hidden_count"]);
      assert.ok(data["chat.feed.loading"]);
      assert.ok(data["chat.feed.failed"]);
    }
  });

  it("prepends older feed items and keeps them when polling the latest page", () => {
    const oldMessage = { kind: "message", message: { ts: "2026-10-01T10:00:00+09:00", content: "old" } };
    const recentMessage = { kind: "message", message: { ts: "2026-10-28T10:00:00+09:00", content: "recent" } };
    const history = createHistoryState();
    applyHistoryData(history, { items: [recentMessage], has_more: true, next_before: oldMessage.message.ts });
    applyHistoryData(history, { items: [oldMessage], has_more: false }, { prepend: true });

    const { changed, merged } = mergePolledHistory(history, {
      items: [{ ...recentMessage, message: { ...recentMessage.message, content: "updated" } }],
      has_more: true,
      next_before: oldMessage.message.ts,
    });

    assert.equal(changed, true);
    assert.equal(merged.isFeed, true);
    assert.deepEqual(merged.feedItems.map((item) => item.message.content), ["old", "updated"]);
    assert.equal(merged.sessions.length, 2);
  });
});
