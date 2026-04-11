// ── Server Communication ────────────────────
import { api } from "../modules/api.js";
import { escapeHtml, timeStr } from "../modules/state.js";
import { onEvent } from "../modules/websocket.js";
import { t } from "/shared/i18n.js";

const _WEEKDAYS_JA = ["日", "月", "火", "水", "木", "金", "土"];

/** Format timestamp: today → "HH:MM", otherwise → "MM/DD(曜) HH:MM" */
function _consolidationTimeStr(isoOrTs) {
  if (!isoOrTs) return "--";
  const d = new Date(isoOrTs);
  if (isNaN(d.getTime())) return "--";
  const time = d.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" });
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  if (sameDay) return time;
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const dow = _WEEKDAYS_JA[d.getDay()];
  if (d.getFullYear() === now.getFullYear()) return `${mm}/${dd}(${dow}) ${time}`;
  return `${d.getFullYear()}/${mm}/${dd}(${dow}) ${time}`;
}

let _refreshInterval = null;
let _unsubConsolidation = null;

export function render(container) {
  container.innerHTML = `
    <div class="page-header">
      <h2>${t("nav.server")}</h2>
    </div>

    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">${t("server.memory_maintenance")}</div>
      <div class="card-body" id="serverConsolidationContent">
        <div class="loading-placeholder">${t("common.loading")}</div>
      </div>
    </div>

    <div class="card-grid" style="grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); margin-bottom: 1.5rem;">
      <div class="stat-card">
        <div class="stat-label">${t("server.uptime_label")}</div>
        <div class="stat-value" id="serverUptime">--</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">${t("server.connections_label")}</div>
        <div class="stat-value" id="serverClients">--</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">${t("server.jobs_label")}</div>
        <div class="stat-value" id="serverJobs">--</div>
      </div>
    </div>

    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">${t("server.ws_connections")}</div>
      <div class="card-body" id="serverWsContent">
        <div class="loading-placeholder">${t("common.loading")}</div>
      </div>
    </div>

    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">${t("server.scheduler_status")}</div>
      <div class="card-body" id="serverSchedulerContent">
        <div class="loading-placeholder">${t("common.loading")}</div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">${t("server.system_status")}</div>
      <div class="card-body" id="serverStatusContent">
        <div class="loading-placeholder">${t("common.loading")}</div>
      </div>
    </div>
  `;

  _loadAll();
  _refreshInterval = setInterval(_loadAll, 15000);

  // Subscribe to consolidation status updates via WebSocket
  _unsubConsolidation = onEvent("system.consolidation_status", (data) => {
    _renderConsolidationData(data);
  });

  // ── Direct action via URL hash parameter ──────────────
  // e.g. /#/server?run=daily  /#/server?run=weekly  /#/server?run=monthly  /#/server?run=catchup
  _handleHashAction();
}

export function destroy() {
  if (_refreshInterval) {
    clearInterval(_refreshInterval);
    _refreshInterval = null;
  }
  if (_unsubConsolidation) {
    _unsubConsolidation();
    _unsubConsolidation = null;
  }
}

// ── Data Loading ───────────────────────────

async function _loadAll() {
  _loadStatus();
  _loadConnections();
  _loadScheduler();
  _loadConsolidation();
}

async function _loadStatus() {
  const statusContent = document.getElementById("serverStatusContent");
  const uptimeEl = document.getElementById("serverUptime");
  if (!statusContent) return;

  try {
    const data = await api("/api/system/status");

    // Server is running if we got a response
    if (uptimeEl) {
      uptimeEl.textContent = t("server.running");
    }

    const rows = [];
    rows.push([t("home.anima_count"), data.animas ?? 0]);
    rows.push([t("server.scheduler"), data.scheduler_running ? t("server.running") : t("server.stopped")]);

    if (data.processes) {
      const processCount = Object.keys(data.processes).length;
      rows.push([t("server.process_count"), processCount]);
    }

    statusContent.innerHTML = `
      <table class="data-table">
        <tbody>
          ${rows.map(([k, v]) => `<tr><td style="font-weight:500;">${escapeHtml(String(k))}</td><td>${escapeHtml(String(v))}</td></tr>`).join("")}
        </tbody>
      </table>
    `;
  } catch (err) {
    if (uptimeEl) uptimeEl.textContent = t("server.stopped");
    statusContent.innerHTML = `<div class="loading-placeholder">${t("server.status_failed")}: ${escapeHtml(err.message)}</div>`;
  }
}

async function _loadConnections() {
  const content = document.getElementById("serverWsContent");
  const clientsEl = document.getElementById("serverClients");
  if (!content) return;

  try {
    const data = await api("/api/system/connections");

    // Read WebSocket client count from response structure
    const wsCount = data.websocket?.connected_clients ?? 0;
    if (clientsEl) clientsEl.textContent = wsCount;

    const rows = [];

    // WebSocket connections summary
    if (wsCount > 0) {
      rows.push(`<tr><td>WebSocket</td><td><code>--</code></td><td>${wsCount} ${t("server.connections_unit")}</td></tr>`);
    }

    // Process connections
    const processes = data.processes || {};
    for (const [name, info] of Object.entries(processes)) {
      const status = info.status || "unknown";
      const pid = info.pid || "--";
      rows.push(`<tr><td>${t("server.process")}</td><td><code>${escapeHtml(name)} (PID: ${pid})</code></td><td>${escapeHtml(status)}</td></tr>`);
    }

    if (rows.length > 0) {
      content.innerHTML = `
        <table class="data-table">
          <thead><tr><th>${t("server.conn_type")}</th><th>${t("server.conn_id")}</th><th>${t("server.conn_state")}</th></tr></thead>
          <tbody>${rows.join("")}</tbody>
        </table>
      `;
    } else {
      content.innerHTML = `<div class="loading-placeholder">${t("server.no_connections")}</div>`;
      if (clientsEl) clientsEl.textContent = "0";
    }
  } catch {
    content.innerHTML = `<div class="loading-placeholder">${t("server.api_unimplemented")}</div>`;
    if (clientsEl) clientsEl.textContent = "--";
  }
}

async function _loadScheduler() {
  const content = document.getElementById("serverSchedulerContent");
  const jobsEl = document.getElementById("serverJobs");
  if (!content) return;

  try {
    const data = await api("/api/system/scheduler");

    const jobs = Array.isArray(data.jobs)
      ? data.jobs
      : [
          ...(Array.isArray(data.system_jobs) ? data.system_jobs : []),
          ...(Array.isArray(data.anima_jobs) ? data.anima_jobs : []),
        ];
    if (jobsEl) jobsEl.textContent = jobs.length;

    if (jobs.length > 0) {
      content.innerHTML = `
        <table class="data-table">
          <thead><tr><th>${t("server.job_name")}</th><th>${t("server.job_person")}</th><th>${t("server.job_schedule")}</th><th>${t("server.job_last_run")}</th><th>${t("server.job_next_run")}</th></tr></thead>
          <tbody>
            ${jobs.map(j => `
              <tr>
                <td style="font-weight:500;">${escapeHtml(j.name || j.id || "--")}</td>
                <td>${escapeHtml(j.anima || "--")}</td>
                <td><code>${escapeHtml(j.schedule || j.trigger || "--")}</code></td>
                <td>${escapeHtml(j.last_run ? timeStr(j.last_run) : "--")}</td>
                <td>${escapeHtml(j.next_run ? timeStr(j.next_run) : "--")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
    } else {
      content.innerHTML = `<div class="loading-placeholder">${t("server.no_jobs")}</div>`;
    }
  } catch {
    content.innerHTML = `<div class="loading-placeholder">${t("server.api_unimplemented")}</div>`;
    if (jobsEl) jobsEl.textContent = "--";
  }
}

// ── Consolidation / Memory Maintenance ───────

const _JOB_DEFS = [
  { key: "daily", labelKey: "server.consolidation_daily" },
  { key: "weekly", labelKey: "server.consolidation_weekly" },
  { key: "monthly", labelKey: "server.consolidation_monthly" },
];

async function _loadConsolidation() {
  const content = document.getElementById("serverConsolidationContent");
  if (!content) return;

  try {
    const data = await api("/api/system/consolidation/status");
    _renderConsolidationData(data);
  } catch {
    content.innerHTML = `<div class="loading-placeholder">${t("server.api_unimplemented")}</div>`;
  }
}

function _renderConsolidationData(data) {
  const content = document.getElementById("serverConsolidationContent");
  if (!content) return;

  const rows = _JOB_DEFS.map(({ key, labelKey }) => {
    const job = data[key] || {};
    const status = job.running ? "running" : (job.missed ? "missed" : (job.last_status || "never"));
    const badge = _statusBadge(status);
    const lastSuccess = _consolidationTimeStr(job.last_success_at);
    const errorText = job.last_error ? escapeHtml(job.last_error) : "";
    const disabled = job.running ? "disabled" : "";

    return `
      <tr>
        <td style="font-weight:500;">${t(labelKey)}</td>
        <td>${badge}</td>
        <td>${escapeHtml(lastSuccess)}</td>
        <td style="color:var(--aw-color-danger,#e53e3e);font-size:0.85em;">${errorText}</td>
        <td>
          <button class="btn btn-sm btn-outline" data-consolidation-run="${key}" ${disabled}>
            ${t("server.consolidation_run")}
          </button>
        </td>
      </tr>
    `;
  }).join("");

  const hasMissed = _JOB_DEFS.some(({ key }) => data[key]?.missed);
  const anyRunning = _JOB_DEFS.some(({ key }) => data[key]?.running);

  content.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>${t("server.job_name")}</th>
          <th>${t("server.consolidation_status")}</th>
          <th>${t("server.consolidation_last_success")}</th>
          <th>${t("server.consolidation_error")}</th>
          <th></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    <div style="margin-top: 0.75rem; text-align: right;">
      <button class="btn btn-sm btn-outline" id="consolidationCatchupBtn" ${anyRunning ? "disabled" : ""}>
        ${t("server.consolidation_catchup")}
      </button>
    </div>
  `;

  // Bind run buttons
  content.querySelectorAll("[data-consolidation-run]").forEach(btn => {
    btn.addEventListener("click", () => _runConsolidation(btn.dataset.consolidationRun));
  });

  // Bind catchup button
  const catchupBtn = document.getElementById("consolidationCatchupBtn");
  if (catchupBtn) {
    catchupBtn.addEventListener("click", _runCatchup);
  }
}

function _statusBadge(status) {
  const labels = {
    success: t("server.consolidation_status_success"),
    failed: t("server.consolidation_status_failed"),
    running: t("server.consolidation_status_running"),
    missed: t("server.consolidation_status_missed"),
    never: t("server.consolidation_status_never"),
  };
  const colors = {
    success: "var(--aw-color-success, #38a169)",
    failed: "var(--aw-color-danger, #e53e3e)",
    running: "var(--aw-color-warning, #d69e2e)",
    missed: "var(--aw-color-warning, #d69e2e)",
    never: "var(--aw-color-text-secondary, #888)",
  };
  const label = labels[status] || status;
  const color = colors[status] || colors.never;
  return `<span style="color:${color};font-weight:500;">${escapeHtml(label)}</span>`;
}

async function _runConsolidation(jobType) {
  // Disable button immediately
  const btn = document.querySelector(`[data-consolidation-run="${jobType}"]`);
  if (btn) btn.disabled = true;

  try {
    await api(`/api/system/consolidation/${jobType}/run`, { method: "POST" });
    // Reload to show running state
    _loadConsolidation();
  } catch (err) {
    if (btn) btn.disabled = false;
    console.error("Consolidation run failed:", err);
  }
}

async function _runCatchup() {
  const btn = document.getElementById("consolidationCatchupBtn");
  if (btn) btn.disabled = true;

  try {
    const result = await api("/api/system/consolidation/catchup", { method: "POST" });
    if (result.error) {
      console.warn("Catchup rejected:", result.error);
    }
    _loadConsolidation();
  } catch (err) {
    if (btn) btn.disabled = false;
    console.error("Catchup failed:", err);
  }
}

// ── Direct Action from URL ─────────────────────
// URLs: /#/server?run=daily | weekly | monthly | catchup

async function _handleHashAction() {
  const hash = location.hash; // e.g. "#/server?run=daily"
  const qIdx = hash.indexOf("?");
  if (qIdx < 0) return;
  const params = new URLSearchParams(hash.slice(qIdx));
  const action = params.get("run");
  if (!action) return;

  // Clean the URL to prevent re-triggering on next navigation
  history.replaceState(null, "", "#/server");

  // Wait for initial data load to finish rendering buttons
  await new Promise((r) => setTimeout(r, 300));

  if (action === "catchup") {
    _runCatchup();
  } else if (["daily", "weekly", "monthly"].includes(action)) {
    _runConsolidation(action);
  }
}
