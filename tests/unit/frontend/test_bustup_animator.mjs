/**
 * Unit tests for bustup-animator.js pure helpers (selectFrameKey, nextMouthState).
 *
 * Run with: node --test tests/unit/frontend/test_bustup_animator.mjs
 *
 * bustup-animator.js imports avatar-resolver via a relative path, which pulls in
 * an absolute "/shared/..." import Node can't resolve — so we load the module
 * source string with that import stubbed (same pattern as other frontend tests).
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = resolve(
  __dirname,
  "../../../server/static/pages/chat/bustup-animator.js",
);

const source = readFileSync(SRC_PATH, "utf8").replace(
  /^import\s*\{[^}]*\}\s*from\s*"\.\.\/\.\.\/modules\/avatar-resolver\.js";?\s*$/m,
  "const assetUrl = (a, f) => `/assets/${a}/${f}`;\n" +
    "const bustupExpressionCandidates = (e) => [`avatar_bustup_${e}.png`];",
);
const moduleUrl =
  "data:text/javascript;base64," + Buffer.from(source, "utf8").toString("base64");
const { selectFrameKey, nextMouthState, MOUTH_THRESHOLDS, MIN_FRAME_HOLD_MS } =
  await import(moduleUrl);

describe("selectFrameKey (フレーム合成)", () => {
  it("maps all 6 (mouth, blinking) combinations to the expected frame key", () => {
    const cases = [
      // (mouth, blinking) -> key
      ["closed", false, "neutral"],
      ["half", false, "half"],
      ["open", false, "open"],
      ["closed", true, "blink"],
      ["half", true, "blinkhalf"],
      ["open", true, "blinkhalf"],
    ];
    for (const [mouth, blinking, expected] of cases) {
      assert.equal(selectFrameKey(mouth, blinking), expected, `${mouth}/${blinking}`);
    }
  });
});

describe("nextMouthState (口パクのヒステリシス)", () => {
  // 前回遷移から十分な時間が経過した状態を起点にする（最短保持を発動させない）
  const settled = (mouth) => ({ mouth, changedAt: 0 });
  const after = 10_000; // now は changedAt より十分後

  it("uses the documented opening thresholds (rising)", () => {
    // closed -> half は 0.06 以上で発動
    assert.equal(nextMouthState(settled("closed"), 0.059, after).mouth, "closed");
    assert.equal(nextMouthState(settled("closed"), 0.06, after).mouth, "half");
    // half -> open は 0.18 以上で発動
    assert.equal(nextMouthState(settled("half"), 0.179, after).mouth, "half");
    assert.equal(nextMouthState(settled("half"), 0.18, after).mouth, "open");
  });

  it("uses 70% thresholds when closing (falling) — hysteresis differs from opening", () => {
    const halfToClosed = MOUTH_THRESHOLDS.closedToHalf * 0.7; // ~0.042
    const openToHalf = MOUTH_THRESHOLDS.halfToOpen * 0.7; // ~0.126

    // open -> half は 0.126 未満で発動
    assert.equal(nextMouthState(settled("open"), openToHalf + 0.01, after).mouth, "open");
    assert.equal(nextMouthState(settled("open"), openToHalf - 0.01, after).mouth, "half");
    // half -> closed は 0.042 未満で発動
    assert.equal(nextMouthState(settled("half"), halfToClosed + 0.01, after).mouth, "half");
    assert.equal(nextMouthState(settled("half"), halfToClosed - 0.01, after).mouth, "closed");
  });

  it("hysteresis: same rms gives different result depending on direction", () => {
    // rms 0.05: 上昇中は closed のまま、下降中は half のまま
    assert.equal(nextMouthState(settled("closed"), 0.05, after).mouth, "closed");
    assert.equal(nextMouthState(settled("half"), 0.05, after).mouth, "half");
  });

  it("enforces the minimum frame hold time (anti-chatter)", () => {
    const s = { mouth: "half", changedAt: 10_000 };
    // まだ最短保持時間を満たしていないので変化しない
    assert.equal(nextMouthState(s, 0.01, 10_000 + MIN_FRAME_HOLD_MS - 1).mouth, "half");
    // 保持時間を超えると変化する
    assert.equal(nextMouthState(s, 0.01, 10_000 + MIN_FRAME_HOLD_MS).mouth, "closed");
    // 上方向にも最短保持が効く
    const s2 = { mouth: "closed", changedAt: 20_000 };
    assert.equal(nextMouthState(s2, 0.9, 20_000 + MIN_FRAME_HOLD_MS - 1).mouth, "closed");
    assert.equal(nextMouthState(s2, 0.9, 20_000 + MIN_FRAME_HOLD_MS).mouth, "half");
  });

  it("records the transition time when the state changes", () => {
    const next = nextMouthState(settled("closed"), 0.1, 12345);
    assert.equal(next.mouth, "half");
    assert.equal(next.changedAt, 12345);
  });

  it("stays stable when the mouth state is already correct at moderate rms", () => {
    // 半開のまま 0.042..0.18 のどこでも維持される
    assert.equal(nextMouthState(settled("half"), 0.07, after).mouth, "half");
    assert.equal(nextMouthState(settled("half"), 0.1, after).mouth, "half");
    // open は 0.126 以上なら維持
    assert.equal(nextMouthState(settled("open"), 0.2, after).mouth, "open");
    // closed は 0.06 未満なら維持
    assert.equal(nextMouthState(settled("closed"), 0.0, after).mouth, "closed");
  });

  it("treats NaN/negative rms as silence", () => {
    assert.equal(nextMouthState(settled("open"), NaN, after).mouth, "half");
    assert.equal(nextMouthState(settled("open"), -1, after).mouth, "half");
  });
});
