// ── Anima status labels ──
// Process/runtime status values come from the server as raw identifiers
// ("running", "not_found", ...). Translate them for display; unknown values
// fall back to the raw identifier so new states stay visible.

import { t } from "/shared/i18n.js";

const STATUS_KEYS = {
  running: "animas.status_running",
  idle: "animas.status_idle",
  starting: "animas.status_starting",
  restarting: "animas.status_restarting",
  bootstrapping: "animas.status_bootstrapping",
  stopped: "animas.status_stopped",
  not_found: "animas.status_stopped",
  offline: "animas.status_offline",
  disabled: "animas.status_disabled",
  error: "animas.status_error",
  down: "animas.status_error",
};

export function animaStatusLabel(status) {
  if (!status) return "";
  const key = STATUS_KEYS[status];
  if (!key) return status;
  const label = t(key);
  return label === key ? status : label;
}
