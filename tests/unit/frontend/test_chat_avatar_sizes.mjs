/** Chat bustups use edge-based WebP sizes appropriate to each display. */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

const faceSource = readFileSync(
  resolve(__dirname, "../../../server/static/shared/chat/emotion-face.js"),
  "utf8",
)
  .replace(/^import \{ isRealisticMode, bustupExpressionCandidates \} from .*;$/m,
    'const isRealisticMode = () => false; const bustupExpressionCandidates = () => ["avatar_bustup.png"];')
  .replace(/^import \{ basePath \} from .*;$/m, 'const basePath = "";');
const faceModuleUrl = "data:text/javascript;base64," + Buffer.from(faceSource, "utf8").toString("base64");
const { bustUrl } = await import(faceModuleUrl);

describe("chat bustup image sizes", () => {
  it("builds P and C URLs for static bustups", () => {
    assert.equal(bustUrl("sakura", "neutral", "P"), "/api/animas/sakura/assets/avatar_bustup.png?size=P");
    assert.equal(bustUrl("sakura", "neutral", "C"), "/api/animas/sakura/assets/avatar_bustup.png?size=C");
  });

  it("uses P for presence panel frames and static fallback", () => {
    const presenceSource = readFileSync(
      resolve(__dirname, "../../../server/static/pages/chat/presence-panel.js"),
      "utf8",
    );
    const animatorSource = readFileSync(
      resolve(__dirname, "../../../server/static/pages/chat/bustup-animator.js"),
      "utf8",
    );
    assert.match(presenceSource, /bustUrl\(name, emotion, "P"\)/);
    assert.match(presenceSource, /new BustupAnimator\(stage, name, "P"\)/);
    assert.match(animatorSource, /assetUrl\(animaName, frameFileFor\(expr, "neutral"\), size\)/);
    assert.match(animatorSource, /assetUrl\(this\._animaName, frameFileFor\(expr, key\), this\._size\)/);
    assert.match(animatorSource, /assetUrl\(this\._animaName, filename, this\._size\)/);
  });

  it("uses C for call screen, PiP and enlarged bustup images", () => {
    const callSource = readFileSync(
      resolve(__dirname, "../../../server/static/pages/chat/call-screen.js"),
      "utf8",
    );
    const avatarSource = readFileSync(
      resolve(__dirname, "../../../server/static/pages/chat/avatar-controller.js"),
      "utf8",
    );
    assert.match(callSource, /animatorFactory\(this\.els\.mainRig, this\.animaName, "C"\)/);
    assert.match(callSource, /animatorFactory\(this\.els\.pipRig, this\.animaName, "C"\)/);
    assert.match(callSource, /resolveCachedAvatar\(this\.animaName, bustupCandidates\(\), "C"\)/);
    assert.match(avatarSource, /bustUrl\(animaName, emotion, "C"\)/);
  });
});
