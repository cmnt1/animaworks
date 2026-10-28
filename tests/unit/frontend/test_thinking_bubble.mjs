/**
 * Unit tests for server/static/shared/chat/thinking-bubble.js
 *
 * Run with: node --test tests/unit/frontend/test_thinking_bubble.mjs
 *
 * The module imports i18n / emotion-face through paths Node cannot resolve
 * (they reach "/shared/..."), so the source is loaded with those imports
 * stubbed and evaluated from a data: URL. `t()` is backed by the real ja.json
 * so the assertions check the shipped wording.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const STATIC = resolve(__dirname, "../../../server/static");
const JA = JSON.parse(readFileSync(resolve(STATIC, "i18n/ja.json"), "utf8"));
globalThis.__thinkTestJa = JA;

const T_STUB = `const t = (key, params = {}) => {
  let text = globalThis.__thinkTestJa[key] || key;
  for (const [k, v] of Object.entries(params)) text = text.replaceAll("{" + k + "}", v);
  return text;
};`;
const HTML_UTILS_URL = pathToFileURL(resolve(STATIC, "shared/html-utils.js")).href;

function load(path, replacements) {
  let source = readFileSync(resolve(STATIC, path), "utf8");
  for (const [re, stub] of replacements) {
    assert.match(source, re, `import to stub not found in ${path}: ${re}`);
    source = source.replace(re, stub);
  }
  return import("data:text/javascript;base64," + Buffer.from(source, "utf8").toString("base64"));
}

const tb = await load("shared/chat/thinking-bubble.js", [
  [/^import\s+\{\s*t\s*\}\s+from\s+["'][^"']+["'];?\s*$/m, T_STUB],
  [/^import\s+\{\s*escapeHtml\s*\}\s+from\s+["'][^"']+["'];?\s*$/m, `import { escapeHtml } from "${HTML_UTILS_URL}";`],
  [/^import\s+\{\s*faceUrl\s*\}\s+from\s+["'][^"']+["'];?\s*$/m,
    "const faceUrl = (name, emotion) => `/face/${name}/${emotion}`;"],
]);

const ru = await load("shared/chat/render-utils.js", [
  [/^import\s+\{\s*t\s*\}\s+from\s+["'][^"']+["'];?\s*$/m, T_STUB],
  [/^import\s+\{\s*escapeAttr\s+as\s+_escapeAttr\s*\}\s+from\s+["'][^"']+["'];?\s*$/m,
    "const _escapeAttr = (value) => String(value);"],
  [/^import\s+\{\s*api\s*\}\s+from\s+["'][^"']+["'];?\s*$/m, "const api = async () => ({});"],
  [/^import\s+\{\s*bustUrl,\s*faceUrl\s*\}\s+from\s+["'][^"']+["'];?\s*$/m, "const bustUrl = () => \"\"; const faceUrl = () => \"\";"],
]);

function streamingMsg(extra = {}) {
  const msg = { role: "assistant", text: "", streaming: true, streamId: "s1", ...extra };
  tb.ensureThink(msg);
  return msg;
}

/** Simulate a text_delta the way streaming-controller does. */
function textDelta(msg, text) {
  msg.text += text;
  return tb.thinkOnText(msg);
}

const renderOpts = {
  escapeHtml: (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`),
  renderMarkdown: (s) => s,
  smartTimestamp: () => "",
  animaName: "mei",
  avatarMap: { mei: "/icon/mei.png" },
  think: tb.thinkRenderHooks,
};

describe("formatElapsed", () => {
  it("formats m:ss and h:mm:ss", () => {
    assert.equal(tb.formatElapsed(0), "0:00");
    assert.equal(tb.formatElapsed(12), "0:12");
    assert.equal(tb.formatElapsed(12.9), "0:12");
    assert.equal(tb.formatElapsed(125), "2:05");
    assert.equal(tb.formatElapsed(3723), "1:02:03");
    assert.equal(tb.formatElapsed(-3), "0:00");
  });

  it("renders the elapsed time since the bubble started", () => {
    const msg = streamingMsg();
    msg.think.startedAt = Date.now() - 12_400;
    const html = tb.renderThinkZone(msg);
    assert.match(html, /class="think-time" data-since="\d+">0:12</);
  });
});

describe("tool labels", () => {
  it("maps known tools to work sentences", () => {
    assert.equal(tb.toolLabel("Read"), "ファイルを読んでいます");
    assert.equal(tb.toolLabel("read_memory_file"), "ファイルを読んでいます");
    assert.equal(tb.toolLabel("Edit"), "ファイルを書いています");
    assert.equal(tb.toolLabel("write_memory_file"), "ファイルを書いています");
    assert.equal(tb.toolLabel("Bash"), "コマンドを実行しています");
    assert.equal(tb.toolLabel("Grep"), "探しています");
    assert.equal(tb.toolLabel("search_memory"), "探しています");
    assert.equal(tb.toolLabel("WebFetch"), "調べています");
    assert.equal(tb.toolLabel("web_search"), "調べています");
    assert.equal(tb.toolLabel("send_message"), "メッセージを送っています");
    assert.equal(tb.toolLabel("delegate_task"), "仕事を頼んでいます");
    assert.equal(tb.toolLabel("TodoWrite"), "段取りを整えています");
    assert.equal(tb.toolLabel("update_task"), "段取りを整えています");
  });

  it("strips MCP prefixes and treats codex command lines as shell", () => {
    assert.equal(tb.toolLabel("mcp__aw__send_message"), "メッセージを送っています");
    assert.equal(tb.toolLabel("mcp__claude_ai_x__web_search"), "調べています");
    assert.equal(tb.toolLabel("bash -lc 'ls -la'"), "コマンドを実行しています");
  });

  it("uses a generic sentence for unknown tools", () => {
    assert.equal(tb.toolLabel("frobnicate"), "frobnicate を使っています");
    assert.equal(tb.toolLabel("mcp__aw__frobnicate"), "frobnicate を使っています");
  });

  it("shortens targets to a path tail or the first 40 characters", () => {
    assert.equal(tb.shortTarget("/home/u/.animaworks/animas/mei/knowledge/nginx-ops.md"), "knowledge/nginx-ops.md");
    const cmd = "certbot certonly --dns-route53 -d example.com -d www.example.com";
    assert.equal(tb.shortTarget(cmd), `${cmd.slice(0, 40)}…`);
    assert.equal(tb.shortTarget(""), "");
  });
});

describe("steps", () => {
  it("starts with a thinking step and adds tool steps", () => {
    const msg = streamingMsg();
    assert.equal(tb.stepCount(msg.think), 1);
    assert.equal(tb.currentLabel(msg), "考えています");

    tb.thinkToolStart(msg, "Read", "t1");
    tb.thinkToolDetail(msg, "t1", "/x/y/knowledge/nginx-ops.md");
    assert.equal(tb.stepCount(msg.think), 2);
    assert.equal(tb.currentLabel(msg), "ファイルを読んでいます");
    assert.equal(tb.activityPhase(msg), "tool");

    const html = tb.renderThinkZone(msg);
    assert.match(html, /<li>考えています<\/li>/);
    assert.match(html, /<li class="now">ファイルを読んでいます <code>knowledge\/nginx-ops\.md<\/code><\/li>/);
    assert.match(html, /手順 2/);
    assert.match(html, /data-think-stop/);
  });

  it("moves the current marker to the newest running tool", () => {
    const msg = streamingMsg();
    tb.thinkToolStart(msg, "Read", "t1");
    tb.thinkToolEnd(msg, { tool_id: "t1" });
    assert.equal(tb.currentLabel(msg), "考えています");
    assert.equal(tb.activityPhase(msg), "thinking");

    tb.thinkToolStart(msg, "Bash", "t2");
    tb.thinkToolDetail(msg, "t2", "gh pr list --state open");
    const html = tb.renderThinkZone(msg);
    assert.equal((html.match(/class="now"/g) || []).length, 1);
    assert.match(html, /<li>ファイルを読んでいます<\/li>/);
    assert.match(html, /<li class="now">コマンドを実行しています <code>gh pr list --state open<\/code><\/li>/);
    assert.match(html, /手順 3/);
  });

  it("marks failed tools", () => {
    const msg = streamingMsg();
    tb.thinkToolStart(msg, "Bash", "t1");
    tb.thinkToolEnd(msg, { tool_id: "t1", is_error: true });
    assert.match(tb.renderThinkZone(msg), /<li class="err">コマンドを実行しています<\/li>/);
  });
});

describe("thinking → reply", () => {
  it("replaces the thinking UI once reply text arrives", () => {
    const msg = streamingMsg();
    tb.thinkToolStart(msg, "Read", "t1");
    tb.thinkToolEnd(msg, { tool_id: "t1" });
    assert.ok(tb.isThinking(msg));
    assert.notEqual(tb.renderThinkZone(msg), "");

    assert.equal(textDelta(msg, "証明書を"), true);
    assert.equal(textDelta(msg, "取りました"), false, "transition fires once");
    assert.equal(tb.isThinking(msg), false);
    assert.equal(tb.renderThinkZone(msg), "");
    assert.equal(tb.currentLabel(msg), "返信を書いています");
    assert.equal(tb.activityPhase(msg), "writing");
  });

  it("folds the steps into 'Steps n' under the finished reply", () => {
    const msg = streamingMsg();
    tb.thinkToolStart(msg, "Read", "t1");
    tb.thinkToolEnd(msg, { tool_id: "t1" });
    tb.thinkToolStart(msg, "Bash", "t2");
    tb.thinkToolEnd(msg, { tool_id: "t2" });
    textDelta(msg, "できました");
    const body = tb.thinkDone(msg, "できました", { emotion: "smile" });
    msg.streaming = false;
    assert.equal(body, "できました");
    assert.equal(tb.activityPhase(msg), "done");

    const fold = tb.renderStepsFold(msg);
    assert.match(fold, /^<details class="think-fold"><summary>手順 3<\/summary>/);
    assert.doesNotMatch(fold, /class="now"/);
  });

  it("skips the fold when nothing but thinking happened", () => {
    const msg = streamingMsg();
    textDelta(msg, "はい");
    tb.thinkDone(msg, "はい");
    assert.equal(tb.renderStepsFold(msg), "");
  });
});

describe("work-in-progress talk (C2)", () => {
  it("keeps text streamed before a tool call out of the reply", () => {
    const msg = streamingMsg();
    textDelta(msg, "Cause confirmed. Unlinking the symlink only.");
    const { moved } = tb.thinkToolStart(msg, "Bash", "t1");
    assert.equal(moved, true);
    assert.equal(msg.text, "", "reply text is reset");
    assert.ok(tb.isThinking(msg), "bubble goes back to the thinking UI");
    assert.match(tb.renderThinkZone(msg), /<li class="say"[^>]*>Cause confirmed\. Unlinking the symlink only\.<\/li>/);
    assert.equal(tb.stepCount(msg.think), 2, "talk is not counted as a step");

    tb.thinkToolEnd(msg, { tool_id: "t1" });
    textDelta(msg, "リンクだけ外しました。");
    const summary = "Cause confirmed. Unlinking the symlink only.\nリンクだけ外しました。";
    const body = tb.thinkDone(msg, summary);
    assert.equal(body, "リンクだけ外しました。");
    assert.match(tb.renderStepsFold(msg), /Cause confirmed/);
  });

  it("falls back to the streamed tail when the summary does not align", () => {
    const msg = streamingMsg();
    textDelta(msg, "checking");
    tb.thinkToolStart(msg, "Read", "t1");
    tb.thinkToolEnd(msg, { tool_id: "t1" });
    textDelta(msg, "答えです");
    assert.equal(tb.thinkDone(msg, "Checking (normalized)\n答えです"), "答えです");
  });

  it("uses the last talk as the reply when a tool came last", () => {
    const msg = streamingMsg();
    textDelta(msg, "送っておきました！");
    tb.thinkToolStart(msg, "send_message", "t1");
    tb.thinkToolEnd(msg, { tool_id: "t1" });
    const body = tb.thinkDone(msg, "送っておきました！");
    assert.equal(body, "送っておきました！");
    assert.doesNotMatch(tb.renderStepsFold(msg), /class="say"/);
  });

  it("uses post-tool text directly when there is no summary", () => {
    const msg = streamingMsg();
    textDelta(msg, "let me look");
    tb.thinkToolStart(msg, "Grep", "t1");
    textDelta(msg, "見つけました");
    assert.equal(tb.thinkDone(msg, msg.text, { aligned: false }), "見つけました");
  });
});

describe("resume", () => {
  it("restores steps and elapsed time from the progress snapshot", () => {
    const startedAt = Date.now() - 65_000;
    const msg = {
      role: "assistant", streaming: true, streamId: "s9",
      text: "Looking at the PR list",
      activeTool: "Bash",
      toolHistory: [
        { tool_name: "Read", tool_id: "a", started_at: startedAt, completed: true, input_summary: "/a/b/notes.md" },
        { tool_name: "Bash", tool_id: "b", started_at: startedAt + 5000, detail: "gh pr list" },
      ],
    };
    tb.restoreThink(msg);
    assert.equal(msg.think.startedAt, startedAt);
    assert.equal(msg.text, "", "talk during a running tool is not reply text");
    const html = tb.renderThinkZone(msg);
    assert.match(html, />1:0[45]</);
    assert.match(html, /<li>ファイルを読んでいます <code>b\/notes\.md<\/code><\/li>/);
    assert.match(html, /<li class="say"[^>]*>Looking at the PR list<\/li><li class="now">コマンドを実行しています <code>gh pr list<\/code><\/li>/);
  });

  it("keeps resumed text as the reply when no tool is running", () => {
    const msg = { role: "assistant", streaming: true, text: "途中まで", toolHistory: [{ tool_name: "Read", completed: true }] };
    tb.restoreThink(msg);
    assert.equal(msg.text, "途中まで");
    assert.equal(tb.isThinking(msg), false);
  });
});

describe("independent bubbles", () => {
  it("gives each stream its own id and state", () => {
    const a = streamingMsg({ streamId: "a" });
    const b = streamingMsg({ streamId: "b" });
    tb.thinkToolStart(a, "Read", "x");
    assert.notEqual(a.think.id, b.think.id);
    assert.equal(tb.stepCount(a.think), 2);
    assert.equal(tb.stepCount(b.think), 1);
  });
});

describe("render-utils integration", () => {
  it("renders a streaming message as the thinking bubble with a thinking face", () => {
    const msg = streamingMsg();
    tb.thinkToolStart(msg, "Read", "t1");
    const html = ru.renderLiveBubble(msg, renderOpts);
    assert.match(html, /class="chat-bubble assistant think-host streaming" data-stream-id="s1"/);
    assert.match(html, /<div class="streaming-zone-text"><\/div>/, "no reply caret while thinking");
    assert.match(html, /class="think"/);
    assert.match(html, /class="chat-msg-avatar think-face thinking"/);
    assert.match(html, /src="\/face\/mei\/thinking" data-fallback-src="\/icon\/mei\.png"/);
  });

  it("renders the reply with a caret once text streams", () => {
    const msg = streamingMsg();
    textDelta(msg, "こんにちは");
    const html = ru.renderLiveBubble(msg, renderOpts);
    assert.match(html, /こんにちは/);
    assert.match(html, /streaming-cursor/);
    assert.doesNotMatch(html, /class="think"/);
    assert.doesNotMatch(html, /think-face thinking/);
  });

  it("renders a finished reply with the steps fold and the emotion face", () => {
    const msg = streamingMsg();
    tb.thinkToolStart(msg, "Read", "t1");
    tb.thinkToolEnd(msg, { tool_id: "t1" });
    msg.toolHistory = [{ tool_name: "Read", tool_id: "t1", completed: true }];
    textDelta(msg, "どうぞ");
    msg.text = tb.thinkDone(msg, "どうぞ", { emotion: "smile" });
    msg.emotion = "smile";
    msg.streaming = false;
    const html = ru.renderLiveBubble(msg, renderOpts);
    assert.match(html, /class="think-fold"/);
    assert.doesNotMatch(html, /tool-activity-timeline/, "old tool timeline is replaced");
    assert.match(html, /src="\/face\/mei\/smile"/);
  });

  it("replaces the Tool Calls group of history messages with the steps fold", () => {
    const msg = {
      role: "assistant", content: "完了", tool_calls: [
        { tool_name: "Read", input: { file_path: "/a/b/c.md" }, result: "ok" },
        { tool_name: "Bash", input: "{\"command\":\"ls -la\"}", is_error: true },
      ],
    };
    const html = ru.renderHistoryMessage(msg, renderOpts);
    assert.match(html, /<summary>手順 2<\/summary>/);
    assert.match(html, /ファイルを読んでいます <code>b\/c\.md<\/code><\/summary><pre>ok<\/pre>/);
    assert.match(html, /<li class="err">コマンドを実行しています <code>ls -la<\/code><\/li>/);
    assert.doesNotMatch(html, /Tool Calls/);

    const plain = ru.renderHistoryMessage(msg, { ...renderOpts, think: undefined });
    assert.match(plain, /Tool Calls \(2\)/, "callers without the hook keep the old group");
  });
});

describe("history fold with progress remarks", () => {
  it("lists remarks spoken before tools as faint steps", () => {
    const html = tb.renderHistorySteps([], { interimTexts: ["Cause confirmed."] });
    assert.match(html, /class="say"/);
    assert.match(html, /Cause confirmed\./);
  });
});
