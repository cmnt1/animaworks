// ── Chat Page (Orchestrator) ──────────────────
import { t } from "/shared/i18n.js";
import { createPaneHost } from "./chat/pane-host.js";

let _host = null;

export function render(container) {
  container.innerHTML = `
    <div class="chat-page-layout" data-chat-id="chatPageLayout">
      <div class="chat-pane-host" data-chat-id="chatPaneHost"></div>
    </div>
  `;

  _host = createPaneHost(container);
  _host.bindSharedEvents();
  _host.restoreLayout();
  if (_host.panes.length === 0) _host.addPane();
}

export function destroy() {
  if (!_host) return;
  _host.destroy();
  _host = null;
}

export function splitPane() {
  return _host?.splitPane() ?? null;
}

function getPaneHost() {
  return _host;
}
