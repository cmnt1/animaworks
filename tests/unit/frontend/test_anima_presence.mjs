import test from "node:test";
import assert from "node:assert/strict";
import {
  createPresenceStore, displayEmotion, displayStatus,
  EMOTION_TTL_MS, PANEL_EMOTION_TTL_MS,
} from "../../../server/static/modules/anima-presence.js";
import { orderRailAnimas, railBadge } from "../../../server/static/pages/chat/rail-logic.js";

test("emotion priority: awaiting > working/calling > recent emotion > neutral", () => {
  const now = 1_000_000;
  const base = { working: false, calling: false, awaitingHuman: false, lastEmotion: "smile", lastEmotionAt: now - 1000 };
  assert.equal(displayEmotion(base, now), "smile");
  assert.equal(displayEmotion({ ...base, working: true }, now), "thinking");
  assert.equal(displayEmotion({ ...base, calling: true }, now), "thinking");
  assert.equal(displayEmotion({ ...base, working: true, awaitingHuman: true }, now), "troubled");
  assert.equal(displayEmotion({ ...base, lastEmotionAt: now - EMOTION_TTL_MS - 1 }, now), "neutral");
  assert.equal(displayEmotion({ ...base, lastEmotion: "bogus" }, now), "neutral");
  assert.equal(displayEmotion(undefined, now), "neutral");
});

test("panel ttl shortens how long the reply emotion stays", () => {
  const now = 5000;
  const e = { lastEmotion: "laugh", lastEmotionAt: now - 9000 };
  assert.equal(displayEmotion(e, now, PANEL_EMOTION_TTL_MS), "neutral");
  assert.equal(displayEmotion(e, now, EMOTION_TTL_MS), "laugh");
});

test("status kind priority", () => {
  assert.equal(displayStatus({ awaitingHuman: true, working: true }), "waiting");
  assert.equal(displayStatus({ calling: true, working: true }), "calling");
  assert.equal(displayStatus({ working: true }), "working");
  assert.equal(displayStatus({}), "idle");
});

test("working is the union of its sources", () => {
  const s = createPresenceStore();
  s.setWorking("mei", true, "stream", "memo");
  s.setWorking("mei", true, "bg");
  s.setWorking("mei", false, "stream");
  assert.equal(s.get("mei").working, true);
  s.setWorking("mei", false, "bg");
  assert.equal(s.get("mei").working, false);
  assert.equal(s.get("mei").label, "");
});

test("subscribe fires only on real changes and can unsubscribe", () => {
  const s = createPresenceStore();
  let n = 0;
  const off = s.subscribe(() => { n++; });
  s.setAwaiting("rin", true);
  s.setAwaiting("rin", true);
  assert.equal(n, 1);
  s.addUnread("rin", 2);
  assert.equal(s.get("rin").unread, 2);
  s.clearUnread("rin");
  assert.equal(n, 3);
  off();
  s.setAwaiting("rin", false);
  assert.equal(n, 3);
});

test("aw:anima-activity phases drive state", () => {
  let t = 100;
  const s = createPresenceStore({ now: () => t });
  s.setAwaiting("mei", true);
  s.applyActivity({ anima: "mei", phase: "thinking", label: "reading" });
  assert.equal(s.get("mei").working, true);
  assert.equal(s.get("mei").awaitingHuman, false, "a stream means the human replied");
  assert.equal(s.get("mei").label, "reading");
  s.applyActivity({ anima: "mei", phase: "done", emotion: "laugh" });
  assert.equal(s.get("mei").working, false);
  assert.equal(s.emotionFor("mei"), "laugh");
  t += EMOTION_TTL_MS + 1;
  assert.equal(s.emotionFor("mei"), "neutral");
  s.applyActivity({ anima: "mei", phase: "call-start" });
  assert.equal(s.statusFor("mei"), "calling");
  s.applyActivity({ anima: "mei", phase: "call-end" });
  assert.equal(s.statusFor("mei"), "idle");
  s.applyActivity({ anima: "mei", phase: "error" });
  assert.equal(s.get("mei").working, false);
  assert.equal(s.applyActivity({ phase: "thinking" }), false);
});

test("applyBusySet replaces only the bg source", () => {
  const s = createPresenceStore();
  s.setWorking("a", true, "stream");
  s.applyBusySet(["a", "b"]);
  assert.equal(s.get("b").working, true);
  s.applyBusySet([]);
  assert.equal(s.get("b").working, false);
  assert.equal(s.get("a").working, true, "stream source untouched by polling");
});

test("pending open is taken once", () => {
  const s = createPresenceStore();
  s.requestOpen("sakura");
  assert.equal(s.takePendingOpen(), "sakura");
  assert.equal(s.takePendingOpen(), null);
});

test("rail ordering keeps open tabs first then adds the rest", () => {
  const animas = [{ name: "a" }, { name: "b" }, { name: "c", enabled: false }, { name: "d" }];
  assert.deepEqual(orderRailAnimas(animas, ["d", "zzz", "a"]).map((x) => x.name), ["d", "a", "b"]);
});

test("rail badge: awaiting wins over unread", () => {
  assert.deepEqual(railBadge({ awaitingHuman: true, unread: 3 }), { kind: "wait", text: "!" });
  assert.deepEqual(railBadge({ awaitingHuman: false, unread: 3 }), { kind: "unread", text: "3" });
  assert.deepEqual(railBadge({ awaitingHuman: false, unread: 120 }), { kind: "unread", text: "99+" });
  assert.equal(railBadge({ awaitingHuman: false, unread: 0 }), null);
});

test("rail leaves hidden animas out unless kept, and lists them for adding back", async () => {
  const { hiddenRailAnimas } = await import("../../../server/static/pages/chat/rail-logic.js");
  const animas = [{ name: "a" }, { name: "b" }, { name: "c" }, { name: "d", enabled: false }];
  const hidden = new Set(["b", "c", "d"]);
  assert.deepEqual(orderRailAnimas(animas, [], hidden).map((x) => x.name), ["a"]);
  assert.deepEqual(orderRailAnimas(animas, [], hidden, new Set(["c"])).map((x) => x.name), ["a", "c"]);
  assert.deepEqual(hiddenRailAnimas(animas, hidden).map((x) => x.name), ["b", "c"]);
});
