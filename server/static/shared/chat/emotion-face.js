// ── Expression face asset URLs shared by chat UI contributors ──
import { isRealisticMode, bustupExpressionCandidates } from "../../modules/avatar-resolver.js";
import { basePath } from "/shared/base-path.js";

const VALID_EMOTIONS = new Set([
  "neutral", "smile", "laugh", "troubled", "surprised", "thinking", "embarrassed",
]);

function _emotionValue(emotion) {
  return VALID_EMOTIONS.has(emotion) ? emotion : "neutral";
}

function _styleValue() {
  return isRealisticMode() ? "realistic" : "anime";
}

/** Return the cached 96/192px face crop URL for a message emotion. */
export function faceUrl(animaName, emotion, size = "S") {
  const style = _styleValue();
  const normalizedSize = size === "M" ? "M" : "S";
  return `${basePath}/api/animas/${encodeURIComponent(animaName)}/assets/face/${_emotionValue(emotion)}?size=${normalizedSize}&style=${style}`;
}

/** Return the emotion-matched bustup URL used by the enlarged face overlay. */
export function bustUrl(animaName, emotion, size = "C") {
  const filename = bustupExpressionCandidates(_emotionValue(emotion))[0];
  return `${basePath}/api/animas/${encodeURIComponent(animaName)}/assets/${encodeURIComponent(filename)}?size=${size}`;
}

/** Update a row's expression thumbnail and accessible emotion metadata. */
export function applyRowEmotion(rowEl, animaName, emotion) {
  if (!rowEl) return;
  const normalizedEmotion = _emotionValue(emotion);
  const face = rowEl.querySelector(".chat-line-face");
  if (!face) return;
  face.src = faceUrl(animaName, normalizedEmotion);
  face.dataset.emotion = normalizedEmotion;
  face.dataset.bustUrl = bustUrl(animaName, normalizedEmotion);
}
