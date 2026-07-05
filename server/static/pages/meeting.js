// ── Meeting Page ─────────────────────────────
import { t } from "/shared/i18n.js";
import { createPaneHost } from "./chat/pane-host.js";

let _host = null;

export function render(container) {
  const title = t("nav.meeting");
  container.innerHTML = `
    <div class="meeting-page-shell">
      <header class="meeting-page-header">
        <h2>${title !== "nav.meeting" ? title : "ミーティング"}</h2>
      </header>
      <div class="chat-page-layout meeting-page-layout sidebar-hidden" data-chat-id="chatPageLayout">
        <div class="chat-pane-host" data-chat-id="chatPaneHost"></div>
      </div>
    </div>
  `;

  _host = createPaneHost(container, {
    meetingStandalone: true,
    singlePane: true,
    disableLayoutRestore: true,
  });
  _host.bindSharedEvents();
  _host.addPane();
}

export function destroy() {
  if (!_host) return;
  _host.destroy();
  _host = null;
}

export function getPaneHost() {
  return _host;
}
