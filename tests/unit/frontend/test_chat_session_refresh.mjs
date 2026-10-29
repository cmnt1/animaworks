/** Session metadata refreshes on change and has a 60-second fallback timer. */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const refreshSource = readFileSync(resolve(__dirname, "../../../server/static/pages/chat/session-refresh.js"), "utf8");
const refreshUrl = "data:text/javascript;base64," + Buffer.from(refreshSource, "utf8").toString("base64");
const { SESSION_REFRESH_INTERVAL_MS, startSessionsRefreshFallback } = await import(refreshUrl);

describe("chat session refresh", () => {
  it("uses a 60-second fallback timer that can be stubbed", () => {
    let tick = null;
    let delay = null;
    let cleared = null;
    let refreshes = 0;
    const stop = startSessionsRefreshFallback(() => { refreshes += 1; }, {
      setInterval(callback, ms) { tick = callback; delay = ms; return 41; },
      clearInterval(id) { cleared = id; },
    });

    assert.equal(SESSION_REFRESH_INTERVAL_MS, 60_000);
    assert.equal(delay, 60_000);
    tick();
    assert.equal(refreshes, 1);
    stop();
    assert.equal(cleared, 41);
  });

  it("keeps sessions out of the five-second chat history poll", () => {
    const rendererSource = readFileSync(resolve(__dirname, "../../../server/static/pages/chat/chat-renderer.js"), "utf8");
    const paneSource = readFileSync(resolve(__dirname, "../../../server/static/pages/chat/pane-host.js"), "utf8");
    const threadSource = readFileSync(resolve(__dirname, "../../../server/static/pages/chat/thread-controller.js"), "utf8");
    const animaSource = readFileSync(resolve(__dirname, "../../../server/static/pages/chat/anima-controller.js"), "utf8");
    const activitySource = readFileSync(resolve(__dirname, "../../../server/static/pages/chat/activity-controller.js"), "utf8");
    const pollBody = rendererSource.match(/async function pollSelectedChat\(\) \{([\s\S]*?)\n  \}/)?.[1] || "";

    assert.ok(pollBody);
    assert.doesNotMatch(pollBody, /\/sessions/);
    assert.match(paneSource, /startSessionsRefreshFallback\(/);
    assert.match(paneSource, /ctx\.controllers\.anima\.refreshSessions\(selected\)/);
    assert.match(threadSource, /ctx\.controllers\.anima\.refreshSessions\(name\)/);
    assert.match(animaSource, /\/summary`/);
    assert.doesNotMatch(animaSource, /api\(`\/api\/animas\/\$\{encodeURIComponent\(name\)\}`\)/);
    assert.match(animaSource, /if \(state\.activeRightTab === "state"\) \{\s*void ctx\.controllers\.memory\.loadMemoryTab\(\);\s*\}/);
    assert.match(activitySource, /\/api\/animas\/\$\{encodeURIComponent\(name\)\}\/state`/);
    assert.doesNotMatch(activitySource, /\/api\/animas\/\$\{encodeURIComponent\(name\)\}`/);
    assert.match(paneSource, /if \(ctx\.state\.activeRightTab === "state"\) \{\s*ctx\.controllers\.activity\.loadAnimaState\(\);\s*ctx\.controllers\.memory\.loadMemoryTab\(\);\s*\}/);
  });
});
