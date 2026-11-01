import test from "node:test";
import assert from "node:assert/strict";
import {
  shouldShowToast, createToastQueue, MAX_TOASTS, AUTO_DISMISS_MS,
} from "../../../server/static/modules/presence-toast.js";

function fakeTimers() {
  let id = 0;
  const pending = new Map();
  return {
    setTimer: (fn, ms) => { pending.set(++id, { fn, ms }); return id; },
    clearTimer: (i) => pending.delete(i),
    pending,
    fire(i) { const p = pending.get(i); pending.delete(i); p?.fn(); },
  };
}

test("not shown while that anima's conversation is on screen", () => {
  assert.equal(shouldShowToast({ kind: "notification", anima: "mei", visibleAnimas: new Set(["mei"]) }), false);
  assert.equal(shouldShowToast({ kind: "reply", anima: "mei", visibleAnimas: ["mei", "rin"] }), false);
  assert.equal(shouldShowToast({ kind: "notification", anima: "mei", visibleAnimas: new Set(["rin"]) }), true);
  assert.equal(shouldShowToast({ kind: "reply", anima: "mei", visibleAnimas: new Set() }), true);
});

test("unknown kind or missing anima never shows", () => {
  assert.equal(shouldShowToast({ kind: "other", anima: "mei", visibleAnimas: [] }), false);
  assert.equal(shouldShowToast({ kind: "reply", anima: "", visibleAnimas: [] }), false);
});

test("at most 3 shown, the rest counted as overflow", () => {
  const q = createToastQueue({ ...fakeTimers() });
  for (const a of ["a", "b", "c", "d", "e"]) q.push({ anima: a, body: a });
  const v = q.view();
  assert.equal(v.shown.length, MAX_TOASTS);
  assert.deepEqual(v.shown.map((x) => x.anima), ["c", "d", "e"]);
  assert.equal(v.overflow, 2);
});

test("auto-dismisses after 8s except urgent", () => {
  const tm = fakeTimers();
  const q = createToastQueue({ ...tm });
  const n = q.push({ anima: "a", body: "x" });
  const u = q.push({ anima: "b", body: "y", priority: "urgent" });
  assert.equal(tm.pending.size, 1);
  assert.equal([...tm.pending.values()][0].ms, AUTO_DISMISS_MS);
  tm.fire([...tm.pending.keys()][0]);
  assert.deepEqual(q.view().shown.map((x) => x.id), [u]);
  assert.ok(n);
});

test("urgent toasts are never pushed out by newer ones", () => {
  const q = createToastQueue({ ...fakeTimers() });
  q.push({ anima: "u", body: "!", priority: "urgent" });
  for (const a of ["a", "b", "c"]) q.push({ anima: a, body: a });
  const v = q.view();
  assert.equal(v.shown.length, MAX_TOASTS);
  assert.ok(v.shown.some((x) => x.anima === "u"));
  assert.equal(v.overflow, 1);
});

test("a newer toast for the same anima and kind replaces the older", () => {
  const q = createToastQueue({ ...fakeTimers() });
  q.push({ anima: "a", kind: "reply", body: "1" });
  q.push({ anima: "a", kind: "reply", body: "2" });
  assert.equal(q.size, 1);
  assert.equal(q.view().shown[0].body, "2");
});

test("dismiss and onChange", () => {
  const seen = [];
  const q = createToastQueue({ ...fakeTimers(), onChange: (v) => seen.push(v.shown.length) });
  const id = q.push({ anima: "a", body: "x" });
  assert.equal(q.dismiss(id), true);
  assert.equal(q.dismiss(id), false);
  assert.deepEqual(seen, [1, 0]);
});
