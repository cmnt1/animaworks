// ── System Status & Office Shell Initialization ──────────────────────
// Timeline, message details, history, and workspace status live outside the
// replaceable office renderer so they remain available for pixel and 3D views.

import { getState } from "./state.js";
import { t } from "../../shared/i18n.js";
import { fetchSystemStatus } from "./api.js";
import { initTimeline, loadHistory } from "./timeline.js";
import { initMessagePopup } from "./message-popup.js";
import { showMessageEffect, showConversation } from "./interactions.js";
import { getActiveRenderer } from "./office-renderer.js";

let officeShellInitialized = false;

function is3dOfficeReady() {
  return getActiveRenderer() === "3d" && getState().officeInitialized;
}

export function initOfficeShell(dom) {
  if (officeShellInitialized) return;

  initTimeline(dom.officePanel, {
    showMessageEffect(...args) {
      if (is3dOfficeReady()) showMessageEffect(...args);
    },
    showConversation(...args) {
      if (is3dOfficeReady()) showConversation(...args);
    },
  });
  initMessagePopup(dom.officePanel);
  loadHistory(24);
  officeShellInitialized = true;
}

// ── System Status ───────────────────────────────────────────────────

export async function loadSystemStatus(dom) {
  if (!dom.systemStatus) return;
  try {
    const data = await fetchSystemStatus();
    updateStatusDisplay(
      dom,
      data.scheduler_running,
      `${t(data.scheduler_running ? "home.scheduler_running" : "home.scheduler_stopped")} (${data.animas}${t("ws.count_suffix")})`
    );
  } catch {
    updateStatusDisplay(dom, false, t("status.connection_failed"));
  }
}

export function updateStatusDisplay(dom, ok, text) {
  if (!dom.systemStatus) return;
  const dot = dom.systemStatus.querySelector(".status-dot");
  const label = dom.systemStatus.querySelector(".status-text");
  if (dot) dot.className = `status-dot ${ok ? "status-idle" : "status-error"}`;
  if (label) label.textContent = text;
}
