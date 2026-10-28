// ── Emotion Face (stub) ─────────────────────────
// Minimal stand-in for workstream A's emotion-face.js so the thinking bubble
// can switch faces. The integrator replaces this file with A's version; keep
// the three exports and their signatures identical.
import { basePath } from "/shared/base-path.js";

function _isRealistic() {
  return typeof document !== "undefined" && document.body?.classList.contains("mode-realistic");
}

export function faceUrl(animaName, emotion, size = "S") {
  const style = _isRealistic() ? "realistic" : "anime";
  const emo = emotion || "neutral";
  return `${basePath}/api/animas/${encodeURIComponent(animaName)}/assets/face/${encodeURIComponent(emo)}?size=${size}&style=${style}`;
}

export function bustUrl(animaName, emotion, size = "L") {
  const suffix = _isRealistic() ? "_realistic" : "";
  const emo = emotion && emotion !== "neutral" ? `_${emotion}` : "";
  const file = `avatar_bustup${emo}${suffix}.png`;
  return `${basePath}/api/animas/${encodeURIComponent(animaName)}/assets/${encodeURIComponent(file)}?size=${size}`;
}

export function applyRowEmotion(rowEl, animaName, emotion) {
  if (!rowEl || !animaName) return;
  const img = rowEl.querySelector(".chat-msg-avatar-img");
  if (img && emotion) {
    if (!img.dataset.fallbackSrc) img.dataset.fallbackSrc = img.getAttribute("src") || "";
    img.src = faceUrl(animaName, emotion);
  }
  if (emotion) rowEl.dataset.emotion = emotion;
}
