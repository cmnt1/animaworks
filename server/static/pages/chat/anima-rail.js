// ── Left rail: every Anima with live status, plus split / meeting tools ──
import { presence, displayStatus } from "../../modules/anima-presence.js";
import { faceUrl } from "../../shared/chat/emotion-face.js";
import { attachFaceFallback } from "./pane-head.js";
import { orderRailAnimas, railBadge } from "./rail-logic.js";

export { orderRailAnimas, railBadge };


export function createAnimaRail({ el, getPanes, getFocused, t, escapeHtml, onToolsChanged }) {
  let _last = "";

  attachFaceFallback(el, (name) => getFocused()?.ctx.state.animaTabAvatarUrls?.[name] || "");

  function render() {
    const focused = getFocused();
    if (!focused) return;
    const fctx = focused.ctx;
    const panes = getPanes();
    const tabNames = fctx.state.animaTabs.map((tab) => tab.name);
    const list = orderRailAnimas(fctx.state.animas, tabNames);
    const active = fctx.state.selectedAnima;
    const others = new Set(
      panes.filter((p) => p !== focused).map((p) => p.ctx.state.selectedAnima).filter(Boolean),
    );

    const items = list.map((a) => {
      const name = a.name;
      const entry = presence.get(name);
      const kind = displayStatus(entry);
      const badge = railBadge(entry);
      const cls = ["chat-rail-item"];
      if (name === active) cls.push("active");
      if (others.has(name)) cls.push("pane2");
      if (kind === "working" || kind === "calling") cls.push("working");
      if (kind === "waiting") cls.push("waiting");
      const stateText = kind === "waiting" ? t("chat.presence.status_waiting")
        : kind === "calling" ? t("chat.presence.status_calling")
          : kind === "working" ? t("chat.presence.status_working") : "";
      const src = faceUrl(name, presence.emotionFor(name), "S");
      const n = escapeHtml(name);
      const fb = fctx.state.animaTabAvatarUrls?.[name];
      if (!fb) fctx.controllers.anima?.ensureAnimaTabAvatar?.(name);
      return `<button type="button" class="${cls.join(" ")}" data-anima="${n}" title="${n}" aria-label="${n}"${name === active ? ' aria-current="true"' : ""}>`
        + `<span class="chat-rail-face"><img src="${escapeHtml(src)}" data-face="${n}" alt=""><span class="chat-rail-ring"></span>`
        + (badge ? `<span class="chat-rail-badge ${badge.kind}">${escapeHtml(badge.text)}</span>` : "")
        + `</span><span class="chat-rail-name">${n}</span><span class="chat-rail-state${kind === "waiting" ? " wait" : ""}">${escapeHtml(stateText)}</span></button>`;
    }).join("");

    const multi = panes.length > 1;
    const full = panes.length >= 4;
    const meetingOn = Boolean(fctx.state.meetingMode);
    const tools = `<span class="chat-rail-sep"></span>`
      + (full ? "" : `<button type="button" class="chat-rail-tool${multi ? " on" : ""}" data-tool="split" title="${escapeHtml(t("pane.split"))}">${escapeHtml(t("chat.presence.rail_split"))}</button>`)
      + `<button type="button" class="chat-rail-tool${meetingOn ? " on" : ""}" data-tool="meeting" title="${escapeHtml(t("meeting.toggle"))}">${escapeHtml(t("chat.presence.rail_meeting"))}</button>`;

    const html = items + tools;
    if (html === _last) return;
    _last = html;
    el.innerHTML = html;

    el.querySelectorAll(".chat-rail-item").forEach((btn) => {
    });
  }

  el.addEventListener("click", (e) => {
    const focused = getFocused();
    if (!focused) return;
    const item = e.target.closest?.(".chat-rail-item");
    if (item) {
      if (item._longPressFired) { item._longPressFired = false; return; }
      const name = item.dataset.anima;
      if (!name) return;
      const anima = focused.ctx.controllers.anima;
      if (name === focused.ctx.state.selectedAnima) focused.ctx.controllers.avatar.showBustupOverlay();
      else anima.openOrSelectAnima(name);
      return;
    }
    const tool = e.target.closest?.(".chat-rail-tool");
    if (tool) {
      const id = tool.dataset.tool === "split" ? "chatSplitPaneBtn" : "meetingModeToggle";
      focused.el.querySelector(`[data-chat-id="${id}"]`)?.click();
      setTimeout(() => { _last = ""; onToolsChanged?.(); }, 50);
    }
  });

  return { render, invalidate() { _last = ""; } };
}
