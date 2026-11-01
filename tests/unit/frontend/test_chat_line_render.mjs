import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const renderUtilsPath = resolve(__dirname, "../../../server/static/shared/chat/render-utils.js");
const replyTargetPath = resolve(__dirname, "../../../server/static/shared/chat/reply-target.js");
const translations = {
  "chat.line.reply": "返信",
  "chat.line.copy": "コピー",
  "chat.line.download": "ダウンロード",
  "chat.line.waiting_reply": "返事待ち",
  "chat.line.from_external": "{via}から",
  "chat.line.sent_external": "{via}で返信",
  "chat.line.read": "既読",
  "chat.human_notify_approve": "承認",
  "chat.human_notify_reject": "却下",
  "chat.human_notify_comment": "コメント",
  "chat.human_notify_resolved": "解決済み",
  "chat.via_slack": "via Slack",
  "chat.meta_source": "Source",
};

const source = readFileSync(renderUtilsPath, "utf8")
  .replace(/^import .*;\r?\n/gm, "");
const stubs = `
  const t = (key, params = {}) => {
    let value = translations[key] || key;
    for (const [name, replacement] of Object.entries(params)) value = value.replaceAll("{" + name + "}", replacement);
    return value;
  };
  const _escapeAttr = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  const api = async () => ({ ok: true });
  const faceUrl = (name, emotion) => "/api/animas/" + encodeURIComponent(name) + "/assets/face/" + (emotion || "neutral");
  const bustUrl = (name, emotion) => "/api/animas/" + encodeURIComponent(name) + "/assets/avatar_bustup_" + (emotion || "neutral") + ".png";
  const translations = ${JSON.stringify(translations)};
`;
const modUrl = "data:text/javascript;base64," + Buffer.from(stubs + source).toString("base64");
const { renderHistoryMessage, renderLiveBubble } = await import(modUrl);
const replyTargetSource = readFileSync(replyTargetPath, "utf8");
const replyTargetUrl = "data:text/javascript;base64," + Buffer.from(replyTargetSource).toString("base64");
const { clearReplyTarget, getReplyTarget, quoteReplyMessage, setReplyTarget } = await import(replyTargetUrl);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
}

const opts = {
  lineChat: true,
  animaName: "mei",
  currentUserNames: new Set(["alice", "Alice Example"]),
  knownAnimaNames: new Set(["mei", "rin"]),
  knownUserNames: new Set(["alice", "Alice Example"]),
  escapeHtml,
  renderMarkdown: (text) => `<p>${escapeHtml(text)}</p>`,
  smartTimestamp: () => "09:05",
};

describe("LINE-style chat message rows", () => {
  it("puts a named expression face on every Anima message", () => {
    const first = renderHistoryMessage({ role: "assistant", content: "First", emotion: "troubled" }, opts);
    const second = renderHistoryMessage({ role: "assistant", content: "Second", emotion: "smile" }, opts);

    for (const html of [first, second]) {
      assert.match(html, /class="chat-line chat-line--anima"/);
      assert.match(html, /class="chat-line-who">mei<\/div>/);
      assert.match(html, /class="chat-line-face"/);
    }
    assert.match(first, /data-emotion="troubled"/);
    assert.match(second, /data-emotion="smile"/);
    assert.match(first, /data-action="reply"/);
    assert.match(first, /data-action="copy"/);
    assert.match(first, /data-action="download"/);
  });

  it("keeps a streaming Anima row in the same layout as a saved reply", () => {
    const live = renderLiveBubble({
      role: "assistant",
      text: "Writing now",
      streaming: true,
      streamId: "stream-1",
    }, opts);
    const saved = renderHistoryMessage({ role: "assistant", content: "Writing now" }, opts);

    for (const html of [live, saved]) {
      assert.match(html, /class="chat-line chat-line--anima"/);
      assert.match(html, /class="chat-line-who">mei<\/div>/);
      assert.match(html, /class="chat-line-face"/);
    }
    assert.match(live, /data-stream-id="stream-1"/);
  });

  it("renders the logged-in user on the right without an avatar and labels Slack", () => {
    const html = renderHistoryMessage({
      role: "human",
      type: "human_reply",
      content: "Approved",
      from_person: "Alice Example",
      via: "slack",
      ts: "2026-10-28T09:05:00+09:00",
    }, opts);

    assert.match(html, /class="chat-line chat-line--me"/);
    assert.doesNotMatch(html, /chat-line-face|chat-line-person-avatar/);
    assert.match(html, /Slackから/);
  });

  it("labels an anima reply that was sent on Slack", () => {
    const html = renderHistoryMessage({
      role: "assistant",
      type: "external_reply",
      content: "確認しました",
      via: "slack",
      ts: "2026-10-28T09:06:00+09:00",
    }, opts);

    assert.doesNotMatch(html, /chat-line--me/);
    assert.match(html, /Slackで返信/);
  });

  it("shows an unmatched human on the left with an initial and name", () => {
    const html = renderHistoryMessage({
      role: "human",
      content: "Hello",
      from_person: "Kai Tanaka",
    }, opts);

    assert.match(html, /class="chat-line chat-line--person"/);
    assert.match(html, /class="chat-line-person-avatar"[^>]*>K</);
    assert.match(html, /class="chat-line-who">Kai Tanaka<\/div>/);
  });

  it("renders a notification as an Anima bubble and marks only unanswered notices", () => {
    const base = {
      role: "system",
      type: "human_notify",
      content: "Please choose an option.",
      subject: "A decision is needed",
      notification_id: "notice-1",
      callback_id: "callback-1",
      ts: "2026-10-28T09:05:00+09:00",
    };
    const waiting = renderHistoryMessage({ ...base, replied: false }, opts);
    const replied = renderHistoryMessage({ ...base, replied: true }, opts);

    assert.match(waiting, /data-notification-id="notice-1"/);
    assert.match(waiting, /class="chat-line chat-line--anima"/);
    assert.match(waiting, /class="chat-line-waiting">返事待ち<\/span>/);
    assert.match(waiting, /class="chat-human-notify-btn"/);
    assert.doesNotMatch(waiting, /class="chat-human-notify[" ]/);
    assert.doesNotMatch(replied, /chat-line-waiting/);
  });

  it("shows an ordinary reply quote at the top of the user's bubble", () => {
    const html = renderHistoryMessage({
      role: "human",
      content: "> We found the cause.\n\nPlease ship the fix.",
      from_person: "alice",
    }, opts);

    assert.match(html, /class="chat-line-quote-text">We found the cause\.<\/div>/);
    assert.match(html, /Please ship the fix\./);
  });

  it("names who is being replied to", () => {
    const named = renderHistoryMessage({ role: "human", content: "> mei: We found the cause.\n\nShip it.", from_person: "alice" }, opts);
    assert.match(named, /chat\.line\.reply_to_name|mei/);
    assert.match(named, /class="chat-line-quote-text">We found the cause\.<\/div>/);
    const notifyReply = renderHistoryMessage({ role: "human", type: "human_reply", content: "Aで", from_person: "alice", reply_quote: "決めてください" }, opts);
    assert.match(notifyReply, /chat-line-quote-text">決めてください/);
  });
});

describe("chat reply targets", () => {
  it("quotes the first 80 characters for ordinary replies and leaves notification replies plain", () => {
    const ordinary = { type: "message", text: "  A reply target with\nseveral spaces.  " };
    const notification = { type: "notification", text: "Please confirm", callbackId: "cb-1" };
    const plainNotice = { type: "notification", text: "Please confirm", name: "aoi" };
    assert.equal(quoteReplyMessage("Ship it", ordinary), "> A reply target with several spaces.\n\nShip it");
    assert.equal(quoteReplyMessage("1", notification), "1");
    assert.equal(quoteReplyMessage("done", plainNotice), "> aoi: Please confirm\n\ndone");
    assert.equal(quoteReplyMessage("reply", { type: "message", text: "x".repeat(100) }), `> ${"x".repeat(80)}\n\nreply`);
  });

  it("stores and clears the target per chat state", () => {
    const state = {};
    setReplyTarget(state, { type: "message", text: "hello" });
    assert.equal(getReplyTarget(state).text, "hello");
    clearReplyTarget(state);
    assert.equal(getReplyTarget(state), null);
  });
});

describe("LINE-style voice call record", () => {
  it("shows the call record with duration and summary in an Anima row", () => {
    const html = renderHistoryMessage({
      role: "assistant",
      type: "voice_call",
      content: "証明書は取得済みと伝えました",
      duration_seconds: 84,
      transcript: [{ speaker: "user", text: "取れた？" }, { speaker: "assistant", text: "取れています" }],
    }, opts);
    assert.match(html, /chat-line--anima/);
    assert.match(html, /class="callrec"/);
    assert.match(html, /chat.call.record_duration/);
    assert.match(html, /証明書は取得済みと伝えました/);
    assert.match(html, /chat-call-transcript/);
  });
});

describe("waiting mark", () => {
  it("is shown only for notifications that need a reply", () => {
    const ask = renderHistoryMessage({ type: "human_notify", role: "system", content: "決めて", replied: false, needs_reply: true }, opts);
    const fyi = renderHistoryMessage({ type: "human_notify", role: "system", content: "記事5件", replied: false, needs_reply: false }, opts);
    assert.match(ask, /chat-line-waiting/);
    assert.doesNotMatch(fyi, /chat-line-waiting/);
  });
});
