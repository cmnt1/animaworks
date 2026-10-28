import test from "node:test";
import assert from "node:assert/strict";
import {
  buildSlashItems, filterSlashItems, slashQuery,
} from "../../../server/static/pages/chat/slash-palette.js";

const t = (k) => k;

test("slashQuery opens only while the first token is typed", () => {
  assert.equal(slashQuery("/"), "");
  assert.equal(slashQuery("/com"), "com");
  assert.equal(slashQuery("/compact "), null);
  assert.equal(slashQuery("hello /x"), null);
  assert.equal(slashQuery(""), null);
  assert.equal(slashQuery("/a/b"), null);
});

test("fixed commands come first and skills never shadow them", () => {
  const items = buildSlashItems([{ name: "compact", ref: "x" }, { name: "review", ref: "common/review", active: true }], t);
  assert.deepEqual(items.map((i) => i.name), ["compact", "thread", "threads", "review"]);
  assert.equal(items[3].kind, "skill");
  assert.equal(items[3].active, true);
  assert.equal(items[3].ref, "common/review");
});

test("filter ranks prefix matches before substring matches", () => {
  const items = buildSlashItems([{ name: "rethread", ref: "r" }], t);
  assert.deepEqual(filterSlashItems(items, "/thr").map((i) => i.name), ["thread", "threads", "rethread"]);
  assert.deepEqual(filterSlashItems(items, "COMP").map((i) => i.name), ["compact"]);
  assert.equal(filterSlashItems(items, "zzz").length, 0);
  assert.equal(filterSlashItems(items, "").length, items.length);
});
