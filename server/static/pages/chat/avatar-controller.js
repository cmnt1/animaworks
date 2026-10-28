// ── Bustup Overlay Controller ──────────────────
import { bustUrl } from "../../shared/chat/emotion-face.js";

export function createAvatarController(ctx) {
  const { state } = ctx;

  async function updateAvatar() {
    if (!state.selectedAnima) {
      state.bustupUrl = null;
      return;
    }
    // Keep the selected Anima's neutral bustup URL for tab-level callers.
    state.bustupUrl = bustUrl(state.selectedAnima, "neutral");
  }

  async function showBustupOverlay(animaName = state.selectedAnima, emotion = "neutral", requestedUrl = "") {
    if (!animaName) return;
    removeBustupOverlay();

    const overlay = document.createElement("div");
    overlay.className = "bustup-overlay";
    overlay.id = "chatBustupOverlay";
    const image = document.createElement("img");
    image.className = "bustup-overlay-img";
    image.src = requestedUrl || bustUrl(animaName, emotion, "L");
    image.alt = `${animaName} (${emotion || "neutral"})`;
    image.addEventListener("error", () => {
      if (image.dataset.fellBack) {
        overlay.remove();
        return;
      }
      image.dataset.fellBack = "1";
      image.src = bustUrl(animaName, "neutral", "L");
    }, { once: false });
    overlay.appendChild(image);
    overlay.addEventListener("click", dismissBustupOverlay);
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add("visible"));
  }

  function dismissBustupOverlay() {
    const overlay = document.getElementById("chatBustupOverlay");
    if (!overlay) return;
    overlay.classList.remove("visible");
    overlay.classList.add("hiding");
    overlay.addEventListener("transitionend", () => overlay.remove(), { once: true });
  }

  function removeBustupOverlay() {
    document.querySelectorAll("#chatBustupOverlay").forEach(el => el.remove());
  }

  function onBustupEscape(e) {
    if (e.key === "Escape") dismissBustupOverlay();
  }

  return { updateAvatar, showBustupOverlay, dismissBustupOverlay, removeBustupOverlay, onBustupEscape };
}
