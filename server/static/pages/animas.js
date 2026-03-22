// ── Anima Management ───────────────────────
import { api } from "../modules/api.js";
import { escapeHtml, statusClass, renderMarkdown } from "../modules/state.js";
import { t } from "/shared/i18n.js";

let _viewMode = "list"; // "list" | "detail"
let _selectedName = null;
let _container = null;
let _modelsCache = null;

function _extractStatsCount(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (value && typeof value === "object") {
    const count = value.count;
    if (typeof count === "number" && Number.isFinite(count)) return count;
  }
  return 0;
}

export function render(container, { subPath } = {}) {
  _container = container;
  if (subPath) {
    _viewMode = "detail";
    _selectedName = subPath;
    _showDetail(subPath);
  } else {
    _viewMode = "list";
    _selectedName = null;
    _renderList();
  }
}

export function destroy() {
  _container = null;
  _viewMode = "list";
  _selectedName = null;
}

// ── List View ──────────────────────────────

async function _renderList() {
  if (!_container) return;

  _container.innerHTML = `
    <div class="page-header">
      <h2>${t("nav.animas")}</h2>
    </div>
    <div id="animasListContent">
      <div class="loading-placeholder">${t("common.loading")}</div>
    </div>
  `;

  const content = document.getElementById("animasListContent");
  if (!content) return;

  try {
    const animas = await api("/api/animas");

    if (animas.length === 0) {
      content.innerHTML = `<div class="loading-placeholder">${t("animas.not_registered")}</div>`;
      return;
    }

    content.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>${t("animas.table_name")}</th>
            <th>${t("animas.table_status")}</th>
            <th>${t("animas.table_pid")}</th>
            <th>${t("animas.table_uptime")}</th>
            <th>${t("animas.table_actions")}</th>
          </tr>
        </thead>
        <tbody id="animasTableBody"></tbody>
      </table>
    `;

    const tbody = document.getElementById("animasTableBody");
    for (const p of animas) {
      const dotClass = statusClass(p.status);
      const statusLabel = p.status || "offline";
      const uptime = p.uptime_sec ? _formatUptime(p.uptime_sec) : "--";
      const pid = p.pid || "--";

      // Determine visual state class
      let stateClass = "";
      if (p.status === "bootstrapping" || p.bootstrapping) {
        stateClass = "anima-item anima-item--loading";
      } else if (p.status === "not_found" || p.status === "stopped") {
        stateClass = "anima-item anima-item--sleeping";
      } else {
        stateClass = "anima-item";
      }

      const tr = document.createElement("tr");
      tr.className = stateClass;
      tr.dataset.anima = p.name;
      tr.style.cursor = "pointer";
      tr.innerHTML = `
        <td style="font-weight:600;">${escapeHtml(p.name)}</td>
        <td>
          <span class="status-dot ${dotClass}" style="display:inline-block;"></span>
          ${escapeHtml(statusLabel)}
        </td>
        <td>${escapeHtml(String(pid))}</td>
        <td>${escapeHtml(uptime)}</td>
        <td>
          <button class="btn-secondary anima-detail-btn" data-name="${escapeHtml(p.name)}" style="font-size:0.8rem; padding:0.25rem 0.5rem;">${t("animas.detail")}</button>
          <button class="btn-primary anima-trigger-btn" data-name="${escapeHtml(p.name)}" style="font-size:0.8rem; padding:0.25rem 0.5rem;">Heartbeat</button>
        </td>
      `;

      tr.addEventListener("click", (e) => {
        if (e.target.classList.contains("anima-trigger-btn")) return;
        _showDetail(p.name);
      });

      tbody.appendChild(tr);
    }

    // Bind trigger buttons
    content.querySelectorAll(".anima-trigger-btn").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const name = btn.dataset.name;
        btn.disabled = true;
        btn.textContent = t("animas.running");
        try {
          await fetch(`/api/animas/${encodeURIComponent(name)}/trigger`, { method: "POST" });
          btn.textContent = t("animas.success");
          setTimeout(() => { btn.textContent = "Heartbeat"; btn.disabled = false; }, 2000);
        } catch {
          btn.textContent = t("animas.failed");
          setTimeout(() => { btn.textContent = "Heartbeat"; btn.disabled = false; }, 2000);
        }
      });
    });

  } catch (err) {
    content.innerHTML = `<div class="loading-placeholder">${t("common.load_failed")}: ${escapeHtml(err.message)}</div>`;
  }
}

// ── Detail View ────────────────────────────

async function _fetchModels() {
  if (_modelsCache) return _modelsCache;
  try {
    const res = await api("/api/system/available-models");
    _modelsCache = res.models || [];
  } catch {
    _modelsCache = [];
  }
  return _modelsCache;
}

function _editableCard({ id, title, rawContent, renderFn }) {
  // Returns HTML for a card with edit/preview toggle and save button
  const rendered = rawContent ? renderFn(rawContent) : `<span style="color:var(--text-secondary,#666);">${t("animas.not_set")}</span>`;
  return `
    <div class="card" id="${id}_card">
      <div class="card-header" style="display:flex; justify-content:space-between; align-items:center;">
        <span>${escapeHtml(title)}</span>
        <div style="display:flex; gap:0.4rem; align-items:center;">
          <span id="${id}_status" style="font-size:0.75rem; color:var(--text-secondary,#888);"></span>
          <button class="btn-secondary" id="${id}_editBtn" style="font-size:0.75rem; padding:0.15rem 0.5rem;">${t("animas.edit")}</button>
          <button class="btn-primary" id="${id}_saveBtn" style="font-size:0.75rem; padding:0.15rem 0.5rem; display:none;">${t("animas.save")}</button>
        </div>
      </div>
      <div class="card-body" style="position:relative;">
        <div id="${id}_preview" style="max-height:300px; overflow-y:auto;">${rendered}</div>
        <textarea id="${id}_editor" style="display:none; width:100%; min-height:260px; max-height:400px; resize:vertical; font-family:monospace; font-size:0.85rem; padding:0.5rem; border:1px solid var(--border,#ddd); border-radius:4px; background:var(--bg-secondary,#f9f9f9); color:var(--text-primary,#333);">${escapeHtml(rawContent || "")}</textarea>
      </div>
    </div>
  `;
}

function _bindEditableCard({ id, name, field }) {
  const editBtn = document.getElementById(`${id}_editBtn`);
  const saveBtn = document.getElementById(`${id}_saveBtn`);
  const preview = document.getElementById(`${id}_preview`);
  const editor = document.getElementById(`${id}_editor`);
  const status = document.getElementById(`${id}_status`);
  if (!editBtn || !saveBtn || !preview || !editor) return;

  let editing = false;

  editBtn.addEventListener("click", () => {
    editing = !editing;
    if (editing) {
      preview.style.display = "none";
      editor.style.display = "block";
      saveBtn.style.display = "";
      editBtn.textContent = t("animas.preview");
      editor.focus();
    } else {
      preview.innerHTML = editor.value
        ? renderMarkdown(editor.value)
        : `<span style="color:var(--text-secondary,#666);">${t("animas.not_set")}</span>`;
      preview.style.display = "";
      editor.style.display = "none";
      saveBtn.style.display = "none";
      editBtn.textContent = t("animas.edit");
    }
  });

  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    saveBtn.textContent = t("animas.saving");
    status.textContent = "";
    try {
      await fetch(`/api/animas/${encodeURIComponent(name)}/${field}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: editor.value }),
      });
      status.textContent = t("animas.saved");
      status.style.color = "var(--color-success, #28a745)";
      // Update preview
      preview.innerHTML = editor.value
        ? renderMarkdown(editor.value)
        : `<span style="color:var(--text-secondary,#666);">${t("animas.not_set")}</span>`;
      setTimeout(() => { status.textContent = ""; }, 3000);
    } catch {
      status.textContent = t("animas.save_failed");
      status.style.color = "var(--color-danger, #dc3545)";
    }
    saveBtn.disabled = false;
    saveBtn.textContent = t("animas.save");
  });
}

// ── Permissions UI ─────────────────────────

function _permissionsCardHtml(perm) {
  const fileRoots = perm.file_roots || [];
  const cmds = perm.commands || {};
  const extTools = perm.external_tools || {};
  const toolCreation = perm.tool_creation || {};

  const pathRows = fileRoots.map((p, i) => `
    <div style="display:flex; align-items:center; gap:0.4rem; margin-bottom:0.3rem;" data-perm-path-row="${i}">
      <input type="text" value="${escapeHtml(p)}" data-perm-path="${i}"
        style="flex:1; padding:0.3rem 0.5rem; font-family:monospace; font-size:0.85rem; border:1px solid var(--border,#ddd); border-radius:4px; background:var(--bg-secondary,#f9f9f9); color:var(--text-primary,#333);">
      <button class="btn-secondary perm-remove-path-btn" data-idx="${i}" style="font-size:0.75rem; padding:0.2rem 0.4rem; color:var(--color-danger,#dc3545);">${t("animas.permissions_remove_path")}</button>
    </div>
  `).join("");

  return `
    <div class="card" style="margin-bottom: 1.5rem;" id="permissionsCard">
      <div class="card-header" style="display:flex; justify-content:space-between; align-items:center;">
        <span>${t("animas.permissions")}</span>
        <div style="display:flex; gap:0.4rem; align-items:center;">
          <span id="permStatus" style="font-size:0.75rem; color:var(--text-secondary,#888);"></span>
          <button class="btn-primary" id="permSaveBtn" style="font-size:0.75rem; padding:0.15rem 0.5rem;">${t("animas.save")}</button>
        </div>
      </div>
      <div class="card-body">
        <!-- file_roots -->
        <div style="margin-bottom:1rem;">
          <label style="font-weight:600; font-size:0.85rem; display:block; margin-bottom:0.4rem;">${t("animas.permissions_file_roots")}</label>
          <div id="permPathList">${pathRows}</div>
          <button class="btn-secondary" id="permAddPathBtn" style="font-size:0.75rem; padding:0.2rem 0.5rem; margin-top:0.3rem;">+ ${t("animas.permissions_add_path")}</button>
        </div>

        <!-- commands -->
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem; margin-bottom:1rem;">
          <fieldset style="border:1px solid var(--border,#ddd); border-radius:4px; padding:0.6rem;">
            <legend style="font-weight:600; font-size:0.85rem; padding:0 0.3rem;">${t("animas.permissions_commands")}</legend>
            <label style="display:flex; align-items:center; gap:0.4rem; font-size:0.85rem; cursor:pointer;">
              <input type="checkbox" id="permCmdAllowAll" ${cmds.allow_all ? "checked" : ""}>
              ${t("animas.permissions_allow_all")}
            </label>
          </fieldset>

          <!-- external_tools -->
          <fieldset style="border:1px solid var(--border,#ddd); border-radius:4px; padding:0.6rem;">
            <legend style="font-weight:600; font-size:0.85rem; padding:0 0.3rem;">${t("animas.permissions_external_tools")}</legend>
            <label style="display:flex; align-items:center; gap:0.4rem; font-size:0.85rem; cursor:pointer;">
              <input type="checkbox" id="permExtAllowAll" ${extTools.allow_all ? "checked" : ""}>
              ${t("animas.permissions_allow_all")}
            </label>
          </fieldset>
        </div>

        <!-- tool_creation -->
        <fieldset style="border:1px solid var(--border,#ddd); border-radius:4px; padding:0.6rem; margin-bottom:0.5rem;">
          <legend style="font-weight:600; font-size:0.85rem; padding:0 0.3rem;">${t("animas.permissions_tool_creation")}</legend>
          <div style="display:flex; gap:1.5rem;">
            <label style="display:flex; align-items:center; gap:0.4rem; font-size:0.85rem; cursor:pointer;">
              <input type="checkbox" id="permToolPersonal" ${toolCreation.personal ? "checked" : ""}>
              ${t("animas.permissions_personal")}
            </label>
            <label style="display:flex; align-items:center; gap:0.4rem; font-size:0.85rem; cursor:pointer;">
              <input type="checkbox" id="permToolShared" ${toolCreation.shared ? "checked" : ""}>
              ${t("animas.permissions_shared")}
            </label>
          </div>
        </fieldset>

        <div style="font-size:0.75rem; color:var(--text-secondary,#888);">${t("animas.restart_notice")}</div>
      </div>
    </div>
  `;
}

function _bindPermissionsCard(name, perm) {
  const saveBtn = document.getElementById("permSaveBtn");
  const status = document.getElementById("permStatus");
  const addBtn = document.getElementById("permAddPathBtn");
  const pathList = document.getElementById("permPathList");
  if (!saveBtn || !pathList) return;

  // Add path button
  addBtn?.addEventListener("click", () => {
    const idx = pathList.querySelectorAll("[data-perm-path-row]").length;
    const row = document.createElement("div");
    row.style.cssText = "display:flex; align-items:center; gap:0.4rem; margin-bottom:0.3rem;";
    row.dataset.permPathRow = idx;
    row.innerHTML = `
      <input type="text" value="" data-perm-path="${idx}"
        style="flex:1; padding:0.3rem 0.5rem; font-family:monospace; font-size:0.85rem; border:1px solid var(--border,#ddd); border-radius:4px; background:var(--bg-secondary,#f9f9f9); color:var(--text-primary,#333);"
        placeholder="/path/to/dir">
      <button class="btn-secondary perm-remove-path-btn" data-idx="${idx}" style="font-size:0.75rem; padding:0.2rem 0.4rem; color:var(--color-danger,#dc3545);">${t("animas.permissions_remove_path")}</button>
    `;
    pathList.appendChild(row);
    // Bind remove
    row.querySelector(".perm-remove-path-btn")?.addEventListener("click", () => row.remove());
    row.querySelector("input")?.focus();
  });

  // Bind remove buttons for initial rows
  pathList.querySelectorAll(".perm-remove-path-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      btn.closest("[data-perm-path-row]")?.remove();
    });
  });

  // Save
  saveBtn.addEventListener("click", async () => {
    // Collect file_roots from inputs
    const paths = [];
    pathList.querySelectorAll("input[data-perm-path]").forEach(inp => {
      const v = inp.value.trim();
      if (v) paths.push(v);
    });

    const updated = {
      version: perm.version || 1,
      file_roots: paths,
      commands: {
        allow_all: document.getElementById("permCmdAllowAll")?.checked ?? true,
        allow: perm.commands?.allow || [],
        deny: perm.commands?.deny || [],
      },
      external_tools: {
        allow_all: document.getElementById("permExtAllowAll")?.checked ?? true,
        allow: perm.external_tools?.allow || [],
        deny: perm.external_tools?.deny || [],
      },
      tool_creation: {
        personal: document.getElementById("permToolPersonal")?.checked ?? true,
        shared: document.getElementById("permToolShared")?.checked ?? false,
      },
    };

    saveBtn.disabled = true;
    saveBtn.textContent = t("animas.saving");
    status.textContent = "";

    try {
      await fetch(`/api/animas/${encodeURIComponent(name)}/permissions`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updated),
      });
      // Update local ref so future saves keep changes
      Object.assign(perm, updated);
      status.textContent = t("animas.saved");
      status.style.color = "var(--color-success, #28a745)";
      setTimeout(() => { status.textContent = ""; }, 3000);
    } catch {
      status.textContent = t("animas.save_failed");
      status.style.color = "var(--color-danger, #dc3545)";
    }
    saveBtn.disabled = false;
    saveBtn.textContent = t("animas.save");
  });
}

// ── Show Detail ───────────────────────────

async function _showDetail(name) {
  if (!_container) return;
  _viewMode = "detail";
  _selectedName = name;

  _container.innerHTML = `
    <div class="page-header" style="display:flex; align-items:center; gap:1rem;">
      <button class="btn-secondary" id="animasBackBtn" style="font-size:0.85rem;">&larr; ${t("animas.back")}</button>
      <h2>${escapeHtml(name)}</h2>
    </div>
    <div id="animasDetailContent">
      <div class="loading-placeholder">${t("common.loading")}</div>
    </div>
  `;

  document.getElementById("animasBackBtn").addEventListener("click", () => {
    window.location.hash = "#/animas";
  });

  const content = document.getElementById("animasDetailContent");
  if (!content) return;

  try {
    const [detail, models] = await Promise.all([
      api(`/api/animas/${encodeURIComponent(name)}`),
      _fetchModels(),
    ]);

    // Try optional endpoints
    let animaConfig = null;
    let memoryStats = null;
    let permissions = {};
    try { animaConfig = await api(`/api/animas/${encodeURIComponent(name)}/config`); } catch { /* 404 ok */ }
    try { memoryStats = await api(`/api/animas/${encodeURIComponent(name)}/memory/stats`); } catch { /* 404 ok */ }
    try { permissions = await api(`/api/animas/${encodeURIComponent(name)}/permissions`); } catch { /* 404 ok */ }

    let html = '<div class="card-grid" style="grid-template-columns: 1fr 1fr; margin-bottom: 1.5rem;">';

    // Identity card (editable)
    html += _editableCard({
      id: "anima_identity",
      title: t("animas.identity"),
      rawContent: detail.identity || "",
      renderFn: renderMarkdown,
    });

    // Injection card (editable)
    html += _editableCard({
      id: "anima_injection",
      title: t("animas.injection"),
      rawContent: detail.injection || "",
      renderFn: renderMarkdown,
    });

    html += "</div>";

    // State + Pending
    html += '<div class="card-grid" style="grid-template-columns: 1fr 1fr; margin-bottom: 1.5rem;">';

    html += `
      <div class="card">
        <div class="card-header">${t("animas.state_current")}</div>
        <div class="card-body">
          <pre style="white-space:pre-wrap; word-break:break-word; margin:0;">${escapeHtml(
            detail.state ? (typeof detail.state === "string" ? detail.state : JSON.stringify(detail.state, null, 2)) : t("animas.no_state")
          )}</pre>
        </div>
      </div>
    `;

    html += `
      <div class="card">
        <div class="card-header">${t("animas.pending")}</div>
        <div class="card-body">
          <pre style="white-space:pre-wrap; word-break:break-word; margin:0;">${escapeHtml(
            detail.pending ? (typeof detail.pending === "string" ? detail.pending : JSON.stringify(detail.pending, null, 2)) : t("animas.no_pending")
          )}</pre>
        </div>
      </div>
    `;

    html += "</div>";

    // Memory stats
    const epCount = detail.episode_files?.length ?? _extractStatsCount(memoryStats?.episodes);
    const knCount = detail.knowledge_files?.length ?? _extractStatsCount(memoryStats?.knowledge);
    const prCount = detail.procedure_files?.length ?? _extractStatsCount(memoryStats?.procedures);

    html += `
      <div class="card-grid" style="grid-template-columns: repeat(3, 1fr); margin-bottom: 1.5rem;">
        <div class="stat-card">
          <div class="stat-label">${t("chat.memory_episodes")}</div>
          <div class="stat-value">${epCount}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">${t("chat.memory_knowledge")}</div>
          <div class="stat-value">${knCount}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">${t("chat.memory_procedures")}</div>
          <div class="stat-value">${prCount}</div>
        </div>
      </div>
    `;

    // Model config (with combobox)
    const currentModel = animaConfig?.model || "";
    const currentCredential = animaConfig?.config?.credential || "";
    html += `
      <div class="card" style="margin-bottom: 1.5rem;">
        <div class="card-header" style="display:flex; justify-content:space-between; align-items:center;">
          <span>${t("animas.model_config")}</span>
          <span id="modelChangeStatus" style="font-size:0.75rem; color:var(--text-secondary,#888);"></span>
        </div>
        <div class="card-body">
          <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:0.75rem; flex-wrap:wrap;">
            <label style="font-weight:600; font-size:0.9rem;">${t("animas.model_select")}:</label>
            <select id="modelSelect" style="flex:1; min-width:200px; padding:0.4rem 0.5rem; border:1px solid var(--border,#ddd); border-radius:4px; font-size:0.85rem; background:var(--bg-secondary,#fff); color:var(--text-primary,#333);">
              ${models.map(m => {
                const selected = m.id === currentModel ? " selected" : "";
                return `<option value="${escapeHtml(m.id)}" data-credential="${escapeHtml(m.credential)}"${selected}>${escapeHtml(m.label)}</option>`;
              }).join("")}
              ${currentModel && !models.find(m => m.id === currentModel) ? `<option value="${escapeHtml(currentModel)}" selected>${escapeHtml(currentModel)} (current)</option>` : ""}
            </select>
            <button class="btn-primary" id="modelChangeBtn" style="font-size:0.85rem; padding:0.4rem 0.75rem;">${t("animas.model_change")}</button>
          </div>
          <div style="font-size:0.75rem; color:var(--text-secondary,#888); margin-bottom:0.75rem;">${t("animas.restart_notice")}</div>
          ${animaConfig ? `<details style="margin-top:0.5rem;"><summary style="cursor:pointer; font-size:0.85rem; color:var(--text-secondary,#666);">JSON</summary><pre style="white-space:pre-wrap; margin:0.5rem 0 0; font-size:0.8rem;">${escapeHtml(JSON.stringify(animaConfig, null, 2))}</pre></details>` : ""}
        </div>
      </div>
    `;

    // Permissions card
    html += _permissionsCardHtml(permissions);

    // Action buttons
    html += `
      <div style="display:flex; gap:0.75rem;">
        <button class="btn-primary" id="animaDetailTrigger">${t("animas.heartbeat_trigger")}</button>
      </div>
    `;

    content.innerHTML = html;

    // Bind editable cards
    _bindEditableCard({ id: "anima_identity", name, field: "identity" });
    _bindEditableCard({ id: "anima_injection", name, field: "injection" });

    // Bind permissions card
    _bindPermissionsCard(name, permissions);

    // Bind model change button
    document.getElementById("modelChangeBtn")?.addEventListener("click", async () => {
      const select = document.getElementById("modelSelect");
      const btn = document.getElementById("modelChangeBtn");
      const status = document.getElementById("modelChangeStatus");
      if (!select || !btn) return;

      const selectedOption = select.options[select.selectedIndex];
      const model = select.value;
      const credential = selectedOption?.dataset?.credential || "";

      btn.disabled = true;
      btn.textContent = t("animas.saving");
      status.textContent = "";

      try {
        await fetch(`/api/animas/${encodeURIComponent(name)}/model`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model, credential }),
        });
        status.textContent = t("animas.model_changed");
        status.style.color = "var(--color-success, #28a745)";
        setTimeout(() => { status.textContent = ""; }, 5000);
      } catch {
        status.textContent = t("animas.model_change_failed");
        status.style.color = "var(--color-danger, #dc3545)";
      }
      btn.disabled = false;
      btn.textContent = t("animas.model_change");
    });

    // Bind trigger button
    document.getElementById("animaDetailTrigger")?.addEventListener("click", async (e) => {
      const btn = e.target;
      btn.disabled = true;
      btn.textContent = t("animas.running");
      try {
        await fetch(`/api/animas/${encodeURIComponent(name)}/trigger`, { method: "POST" });
        btn.textContent = t("animas.success");
        setTimeout(() => { btn.textContent = t("animas.heartbeat_trigger"); btn.disabled = false; }, 2000);
      } catch {
        btn.textContent = t("animas.failed");
        setTimeout(() => { btn.textContent = t("animas.heartbeat_trigger"); btn.disabled = false; }, 2000);
      }
    });

  } catch (err) {
    content.innerHTML = `<div class="loading-placeholder">${t("animas.detail_load_failed")}: ${escapeHtml(err.message)}</div>`;
  }
}

// ── Helpers ────────────────────────────────

function _formatUptime(seconds) {
  if (!seconds || seconds < 0) return "--";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return t("animas.uptime_hm", { h, m });
  return t("animas.uptime_m", { m });
}
