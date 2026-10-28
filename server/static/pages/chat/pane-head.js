// ── Pane header: face / name / status + thread tab labels ──
import { presence, displayStatus } from "../../modules/anima-presence.js";
import { openWaitingList } from "./waiting-list.js";
import { faceUrl } from "../../shared/chat/emotion-face.js";

const THREAD_LABEL_MAX = 20;

/** Letter-in-a-circle placeholder used when no image can be loaded. */
export function initialFaceUri(name) {
  const ch = (String(name || "?").trim().charAt(0) || "?").toUpperCase()
    .replace(/&/g, "&amp;").replace(/</g, "&lt;");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44"><rect width="44" height="44" fill="#cbd5e1"/><text x="22" y="29" font-size="20" font-family="sans-serif" text-anchor="middle" fill="#475569">${ch}</text></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

/** Swap a failed face image for its fallback (the plain icon, else an initial). */
export function attachFaceFallback(rootEl, resolveFallback) {
  rootEl.addEventListener("error", (e) => {
    const img = e.target;
    if (!(img instanceof HTMLImageElement) || img.dataset.face == null) return;
    if (img.dataset.faceFailed) return;
    const fb = resolveFallback(img.dataset.face) || initialFaceUri(img.dataset.face);
    img.dataset.faceFailed = "1";
    img.src = fb;
  }, true);
}

export function statusText(t, entry) {
  const kind = displayStatus(entry);
  if (kind === "waiting") return t("chat.presence.status_waiting");
  if (kind === "calling") return t("chat.presence.status_calling");
  if (kind === "working") {
    const base = t("chat.presence.status_working");
    return entry.label ? `${base} · ${entry.label}` : base;
  }
  return t("chat.presence.status_idle");
}

export function createPaneHead(ctx) {
  const $ = ctx.$;
  const { state, deps } = ctx;
  const { t } = deps;

  const root = ctx.state.container;
  attachFaceFallback(root, (name) => state.animaTabAvatarUrls?.[name] || "");

  // "Waiting for reply" in the header opens the list of notifications to answer.
  root?.addEventListener("click", (e) => {
    const status = e.target.closest?.('[data-chat-id="chatPaneHeadStatus"].wait');
    if (!status || !state.selectedAnima) return;
    openWaitingList({
      anchor: status,
      anima: state.selectedAnima,
      getFocused: () => ({ ctx }),
      t,
      escapeHtml: deps.escapeHtml,
    });
  });

  function refresh() {
    const name = state.selectedAnima;
    const face = $("chatPaneHeadFace");
    const nameEl = $("chatPaneHeadName");
    const statusEl = $("chatPaneHeadStatus");
    if (!face || !nameEl || !statusEl) return;
    if (!name) {
      face.hidden = true;
      nameEl.textContent = "";
      statusEl.textContent = "";
      return;
    }
    const entry = presence.get(name);
    const src = faceUrl(name, presence.emotionFor(name), "S");
    face.hidden = false;
    face.dataset.face = name;
    if (face.dataset.src !== src) {
      face.dataset.src = src;
      delete face.dataset.faceFailed;
      face.src = src;
    }
    nameEl.textContent = name;
    statusEl.textContent = statusText(t, entry);
    const kind = displayStatus(entry);
    statusEl.classList.toggle("on", kind === "working" || kind === "calling");
    statusEl.classList.toggle("wait", kind === "waiting");
  }

  /**
   * Thread tabs: show the first words of the first user message instead of the
   * generic label; the original label (a timestamp) moves to the tooltip.
   */
  function decorateThreadTabs() {
    const container = $("chatThreadTabs");
    const name = state.selectedAnima;
    if (!container || !name) return;
    container.querySelectorAll(".thread-tab[data-thread]").forEach((btn) => {
      const tid = btn.dataset.thread;
      if (!tid || tid === "default") return;
      let msgs = [];
      try { msgs = state.manager.getMessages(name, tid) || []; } catch { /* no session yet */ }
      const first = msgs.find((m) => m.role === "user" && typeof m.text === "string" && m.text.trim());
      if (!first) return;
      const flat = first.text.trim().replace(/\s+/g, " ");
      const label = flat.length > THREAD_LABEL_MAX ? `${flat.slice(0, THREAD_LABEL_MAX)}…` : flat;
      const textNode = [...btn.childNodes].find((n) => n.nodeType === 3);
      if (!textNode) return;
      btn.title = textNode.textContent.trim() || btn.title;
      textNode.textContent = label;
    });
  }

  return { refresh, decorateThreadTabs };
}
