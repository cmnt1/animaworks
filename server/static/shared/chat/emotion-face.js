/**
 * Emotion face / bust-up URL helpers.
 *
 * Interim version holding only the shared contract (faceUrl / bustUrl /
 * applyRowEmotion); the full implementation is owned by the bubble workstream.
 */
import { basePath } from "/shared/base-path.js";

const EMOTIONS = new Set([
  "neutral", "smile", "laugh", "troubled", "surprised", "thinking", "embarrassed",
]);

function _style() {
  return document.body.classList.contains("mode-realistic") ? "realistic" : "anime";
}

function _emotion(e) {
  return EMOTIONS.has(e) ? e : "neutral";
}

/** Round face icon for an emotion. size: "S" | "M". */
export function faceUrl(animaName, emotion, size = "S") {
  const name = encodeURIComponent(animaName);
  return `${basePath}/api/animas/${name}/assets/face/${_emotion(emotion)}?size=${size}&style=${_style()}`;
}

/** Bust-up image for an emotion. */
export function bustUrl(animaName, emotion, size = "L") {
  const e = _emotion(emotion);
  const real = _style() === "realistic" ? "_realistic" : "";
  const file = e === "neutral" ? `avatar_bustup${real}.png` : `avatar_bustup_${e}${real}.png`;
  return `${basePath}/api/animas/${encodeURIComponent(animaName)}/assets/${file}?size=${size}`;
}

/** Switch a reply row's icon to the given emotion and tag it. */
export function applyRowEmotion(rowEl, animaName, emotion) {
  if (!rowEl) return;
  const e = _emotion(emotion);
  rowEl.dataset.emotion = e;
  const img = rowEl.querySelector("img");
  if (img) img.src = faceUrl(animaName, e, "S");
}
