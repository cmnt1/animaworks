// ── Setup Status ────────────────────────────
import { api } from "../modules/api.js";
import { escapeHtml } from "../modules/state.js";
import { t } from "/shared/i18n.js";

export function render(container) {
  container.innerHTML = `
    <div class="page-header">
      <h2>${t("setup.page_title")}</h2>
    </div>

    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">${t("setup.check_init")}</div>
      <div class="card-body" id="setupChecklist">
        <div class="loading-placeholder">${t("common.loading")}</div>
      </div>
    </div>

    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">${t("setup.config_current")}</div>
      <div class="card-body" id="setupConfig">
        <div class="loading-placeholder">${t("common.loading")}</div>
      </div>
    </div>

    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">${t("setup.api_keys")}</div>
      <div class="card-body" id="setupApiKeys">
        <div class="loading-placeholder">${t("common.loading")}</div>
      </div>
    </div>

    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">${t("setup.openai_auth")}</div>
      <div class="card-body" id="openaiAuthSettings">
        <div class="loading-placeholder">${t("common.loading")}</div>
      </div>
    </div>

    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">${t("setup.auth_settings")}</div>
      <div class="card-body" id="authSettings">
        <div class="loading-placeholder">${t("common.loading")}</div>
      </div>
    </div>
  `;

  _loadChecklist();
  _loadConfig();
  _loadOpenAIAuthSettings();
  _loadAuthSettings();
}

export function destroy() {
  // No intervals to clean up
}

// ── Checklist ──────────────────────────────

async function _loadChecklist() {
  const el = document.getElementById("setupChecklist");
  if (!el) return;

  let initData = null;
  let systemData = null;
  let animas = [];

  // Try init-status endpoint first
  try {
    initData = await api("/api/system/init-status");
  } catch { /* may not exist */ }

  // Fallback: infer from other endpoints
  try {
    systemData = await api("/api/system/status");
  } catch { /* ignore */ }

  try {
    animas = await api("/api/animas");
  } catch { /* ignore */ }

  const checks = [];

  if (initData) {
    // Use init-status data
    if (Array.isArray(initData.checks)) {
      // Structured checks array format
      for (const item of initData.checks) {
        const label = item.detail ? `${item.label} (${item.detail})` : item.label;
        checks.push({ label, ok: !!item.ok });
      }
    } else {
      // Legacy flat object format — use truthy evaluation
      const items = initData.checks || initData;
      if (typeof items === "object") {
        for (const [key, val] of Object.entries(items)) {
          const ok = !!val && val !== "error" && val !== "missing";
          checks.push({ label: key, ok });
        }
      }
    }
  } else {
    // Infer status
    checks.push({ label: t("setup.check_server"), ok: !!systemData });
    checks.push({ label: t("setup.check_person_dir"), ok: animas.length > 0 });
    checks.push({ label: t("setup.check_scheduler"), ok: systemData?.scheduler_running ?? false });
  }

  if (checks.length === 0) {
    el.innerHTML = `<div class="loading-placeholder">${t("setup.check_failed")}</div>`;
    return;
  }

  el.innerHTML = checks.map(c => `
    <div style="display:flex; align-items:center; gap:0.75rem; padding:0.5rem 0; border-bottom:1px solid var(--border-color, #eee);">
      <span style="font-size:1.2rem;">${c.ok ? "\u2705" : "\u274C"}</span>
      <span>${escapeHtml(c.label)}</span>
    </div>
  `).join("");
}

// ── Config ────────────────────────────────

async function _loadConfig() {
  const configEl = document.getElementById("setupConfig");
  const keysEl = document.getElementById("setupApiKeys");
  if (!configEl) return;

  try {
    const config = await api("/api/system/config");

    // Render config table
    const rows = [];
    function flattenConfig(obj, prefix = "") {
      for (const [key, val] of Object.entries(obj)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;
        if (val && typeof val === "object" && !Array.isArray(val)) {
          flattenConfig(val, fullKey);
        } else {
          // Mask potential secrets
          let displayVal = String(val);
          if (/key|secret|token|password/i.test(key) && displayVal.length > 4) {
            displayVal = displayVal.slice(0, 4) + "****";
          }
          rows.push({ key: fullKey, val: displayVal });
        }
      }
    }
    flattenConfig(config);

    configEl.innerHTML = `
      <div class="data-table-wrapper">
        <table class="data-table">
          <thead><tr><th>${t("setup.config_key")}</th><th>${t("setup.config_value")}</th></tr></thead>
          <tbody>
            ${rows.map(r => `<tr><td>${escapeHtml(r.key)}</td><td><code>${escapeHtml(r.val)}</code></td></tr>`).join("")}
          </tbody>
        </table>
      </div>
    `;

    // Extract API key info
    if (keysEl) {
      const keyEntries = rows.filter(r => /key|api_key|token/i.test(r.key));
      if (keyEntries.length > 0) {
        keysEl.innerHTML = keyEntries.map(k => {
          const configured = k.val && k.val !== "null" && k.val !== "None" && k.val !== "";
          return `
            <div style="display:flex; align-items:center; gap:0.75rem; padding:0.5rem 0; border-bottom:1px solid var(--border-color, #eee);">
              <span style="font-size:1.2rem;">${configured ? "\u2705" : "\u274C"}</span>
              <span style="font-weight:500;">${escapeHtml(k.key)}</span>
              <code style="margin-left:auto; color:var(--text-secondary, #666);">${escapeHtml(k.val)}</code>
            </div>
          `;
        }).join("");
      } else {
        keysEl.innerHTML = `<div class="loading-placeholder">${t("setup.api_keys_not_in_config")}</div>`;
      }
    }
  } catch {
    configEl.innerHTML = `<div class="loading-placeholder">${t("setup.api_unimplemented")}</div>`;
    if (keysEl) keysEl.innerHTML = `<div class="loading-placeholder">${t("setup.config_unavailable")}</div>`;
  }
}

// ── Auth Settings ──────────────────────────

async function _loadAuthSettings() {
  const el = document.getElementById("authSettings");
  if (!el) return;

  try {
    const me = await api("/api/auth/me");
    const users = await api("/api/users");

    let html = "";

    // Auth mode info
    const modeLabel = { local_trust: t("setup.auth_local_trust"), password: t("setup.auth_password"), multi_user: t("setup.auth_multi_user") };
    html += `<div style="margin-bottom: 1rem;">
      <strong>${t("setup.auth_mode")}:</strong> <code>${escapeHtml(modeLabel[me.auth_mode] || me.auth_mode || t("common.unknown"))}</code>
    </div>`;

    // Password change / initial setup form
    const isInitial = !me.has_password;
    const skipCurrentPw = me.auth_mode === "local_trust";
    html += `
      <div style="margin-bottom: 1.5rem;">
        <h4 style="margin-bottom: 0.5rem;">${isInitial ? t("setup.password_set") : t("setup.password_change")}</h4>
        <form id="changePasswordForm" style="display:flex; flex-direction:column; gap:0.5rem; max-width:300px;">
          ${isInitial || skipCurrentPw ? "" : `<input type="password" id="currentPassword" placeholder="${t("setup.password_current")}" required>`}
          <input type="password" id="newPassword" placeholder="${t("setup.password_new")}" required>
          <input type="password" id="confirmPassword" placeholder="${t("setup.password_confirm")}" required>
          <div id="pwChangeResult" class="login-error hidden"></div>
          <button type="submit" class="btn-login" style="width:auto;">${isInitial ? t("setup.password_set_btn") : t("setup.password_change_btn")}</button>
        </form>
      </div>
    `;

    // User management (owner only)
    if (me.role === "owner") {
      html += `
        <div style="margin-bottom: 1.5rem;">
          <h4 style="margin-bottom: 0.5rem;">${t("setup.user_management")}</h4>
          <table class="data-table">
            <thead><tr><th>${t("setup.user_username")}</th><th>${t("setup.user_displayname")}</th><th>${t("setup.user_role")}</th><th>${t("setup.user_actions")}</th></tr></thead>
            <tbody>
              ${users.map(u => `
                <tr>
                  <td>${escapeHtml(u.username)}</td>
                  <td>${escapeHtml(u.display_name)}</td>
                  <td>${escapeHtml(u.role)}</td>
                  <td>${u.role !== "owner" ? `<button class="btn-delete-user" data-user="${escapeHtml(u.username)}" style="color:#ef4444;cursor:pointer;border:none;background:none;">${t("setup.user_delete")}</button>` : "-"}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>

        <div>
          <h4 style="margin-bottom: 0.5rem;">${t("setup.user_add")}</h4>
          <form id="addUserForm" style="display:flex; flex-direction:column; gap:0.5rem; max-width:300px;">
            <input type="text" id="newUsername" placeholder="${t("setup.user_username")}" required>
            <input type="text" id="newDisplayName" placeholder="${t("setup.user_displayname")}">
            <input type="password" id="newUserPassword" placeholder="${t("setup.user_password")}" required>
            <div id="addUserResult" class="login-error hidden"></div>
            <button type="submit" class="btn-login" style="width:auto;">${t("setup.user_add_btn")}</button>
          </form>
        </div>
      `;
    }

    el.innerHTML = html;

    // Password change handler
    const pwForm = document.getElementById("changePasswordForm");
    if (pwForm) {
      pwForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const result = document.getElementById("pwChangeResult");
        const newPw = document.getElementById("newPassword").value;
        const confirmPw = document.getElementById("confirmPassword").value;

        if (newPw !== confirmPw) {
          result.textContent = t("setup.password_mismatch");
          result.classList.remove("hidden");
          return;
        }

        try {
          const curPwEl = document.getElementById("currentPassword");
          const res = await fetch("/api/users/me/password", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({
              current_password: curPwEl ? curPwEl.value : "",
              new_password: newPw,
            }),
          });
          const data = await res.json();
          if (res.ok) {
            const willReload = isInitial || skipCurrentPw;
            result.textContent = willReload ? t("setup.password_set_success") : t("setup.password_change_success");
            result.style.color = "#22c55e";
            result.classList.remove("hidden");
            pwForm.reset();
            if (willReload) setTimeout(() => location.reload(), 1000);
          } else {
            result.style.color = "#ef4444";
            result.textContent = data.error || t("setup.password_failed");
            result.classList.remove("hidden");
          }
        } catch {
          result.style.color = "#ef4444";
          result.textContent = t("setup.network_error");
          result.classList.remove("hidden");
        }
      });
    }

    // Delete user handlers
    el.querySelectorAll(".btn-delete-user").forEach(btn => {
      btn.addEventListener("click", async () => {
        const username = btn.dataset.user;
        if (!confirm(t("setup.user_delete_confirm", { username }))) return;

        try {
          const res = await fetch(`/api/users/${username}`, {
            method: "DELETE",
            credentials: "same-origin",
          });
          if (res.ok) {
            _loadAuthSettings(); // Reload
          } else {
            const data = await res.json();
            alert(data.error || t("setup.user_delete_failed"));
          }
        } catch {
          alert(t("setup.network_error"));
        }
      });
    });

    // Add user handler
    const addForm = document.getElementById("addUserForm");
    if (addForm) {
      addForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const result = document.getElementById("addUserResult");

        try {
          const res = await fetch("/api/users", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({
              username: document.getElementById("newUsername").value.trim(),
              display_name: document.getElementById("newDisplayName").value.trim(),
              password: document.getElementById("newUserPassword").value,
            }),
          });
          const data = await res.json();
          if (res.ok) {
            result.textContent = t("setup.user_add_success", { username: data.username });
            result.style.color = "#22c55e";
            result.classList.remove("hidden");
            addForm.reset();
            _loadAuthSettings(); // Reload user list
          } else {
            result.style.color = "#ef4444";
            result.textContent = data.error || t("setup.user_add_failed");
            result.classList.remove("hidden");
          }
        } catch {
          result.style.color = "#ef4444";
          result.textContent = t("setup.network_error");
          result.classList.remove("hidden");
        }
      });
    }
  } catch {
    el.innerHTML = `<div class="loading-placeholder">${t("setup.auth_fetch_failed")}</div>`;
  }
}

// ── OpenAI / Codex Auth ───────────────────

async function _loadOpenAIAuthSettings() {
  const el = document.getElementById("openaiAuthSettings");
  if (!el) return;

  try {
    const state = await api("/api/settings/openai-auth");
    const modeLabel = state.auth_mode === "codex_login"
      ? t("setup.openai_auth_mode_codex")
      : t("setup.openai_auth_mode_api");

    const runtimeBadges = [
      {
        label: t("setup.openai_auth_env_key"),
        ok: !!state.env_api_key_configured,
      },
      {
        label: t("setup.openai_auth_codex_cli"),
        ok: !!state.codex_cli_available,
      },
      {
        label: t("setup.openai_auth_codex_login"),
        ok: !!state.codex_login_available,
      },
    ];

    el.innerHTML = `
      <div style="margin-bottom: 1rem;">
        <strong>${t("setup.openai_auth_current")}:</strong>
        <code>${escapeHtml(modeLabel)}</code>
      </div>
      <div style="margin-bottom: 1rem;">
        <strong>${t("setup.openai_auth_saved")}:</strong>
        <span>${state.config_present ? t("setup.openai_auth_saved_yes") : t("setup.openai_auth_saved_no")}</span>
      </div>
      <div style="display:grid; gap:0.5rem; margin-bottom: 1.25rem;">
        ${runtimeBadges.map(item => `
          <div style="display:flex; align-items:center; gap:0.75rem;">
            <span style="font-size:1.1rem;">${item.ok ? "\u2705" : "\u274C"}</span>
            <span>${escapeHtml(item.label)}</span>
          </div>
        `).join("")}
      </div>

      <form id="openaiAuthForm" style="display:flex; flex-direction:column; gap:0.75rem; max-width:420px;">
        <label style="display:flex; flex-direction:column; gap:0.35rem;">
          <span>${t("setup.openai_auth_mode_label")}</span>
          <select id="openaiAuthMode">
            <option value="api_key"${state.auth_mode === "api_key" ? " selected" : ""}>${t("setup.openai_auth_mode_api")}</option>
            <option value="codex_login"${state.auth_mode === "codex_login" ? " selected" : ""}>${t("setup.openai_auth_mode_codex")}</option>
          </select>
        </label>
        <label id="openaiApiKeyWrap" style="display:${state.auth_mode === "api_key" ? "flex" : "none"}; flex-direction:column; gap:0.35rem;">
          <span>${t("setup.openai_auth_api_key")}</span>
          <input type="password" id="openaiApiKeyInput" placeholder="${t("setup.openai_auth_api_key_placeholder")}">
          <small style="color:var(--text-secondary, #666);">${t("setup.openai_auth_api_key_hint")}</small>
        </label>
        <div id="openaiAuthResult" class="login-error hidden"></div>
        <button type="submit" class="btn-login" style="width:auto;">${t("setup.openai_auth_save")}</button>
      </form>
    `;

    const modeEl = document.getElementById("openaiAuthMode");
    const apiKeyWrap = document.getElementById("openaiApiKeyWrap");
    modeEl?.addEventListener("change", () => {
      if (apiKeyWrap) {
        apiKeyWrap.style.display = modeEl.value === "api_key" ? "flex" : "none";
      }
    });

    const form = document.getElementById("openaiAuthForm");
    form?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const result = document.getElementById("openaiAuthResult");
      const authMode = document.getElementById("openaiAuthMode").value;
      const apiKey = document.getElementById("openaiApiKeyInput")?.value || "";

      if (authMode === "api_key" && !apiKey.trim()) {
        result.style.color = "#ef4444";
        result.textContent = t("setup.openai_auth_api_key_required");
        result.classList.remove("hidden");
        return;
      }

      try {
        const validateRes = await fetch("/api/setup/validate-key", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({
            provider: "openai",
            auth_mode: authMode,
            api_key: apiKey,
          }),
        });
        const validateData = await validateRes.json();
        if (!validateRes.ok || !validateData.valid) {
          result.style.color = "#ef4444";
          result.textContent = validateData.message || validateData.detail || t("setup.openai_auth_save_failed");
          result.classList.remove("hidden");
          return;
        }

        const saveRes = await fetch("/api/settings/openai-auth", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({
            auth_mode: authMode,
            api_key: apiKey,
          }),
        });
        const saveData = await saveRes.json();
        if (!saveRes.ok) {
          result.style.color = "#ef4444";
          result.textContent = saveData.detail || t("setup.openai_auth_save_failed");
          result.classList.remove("hidden");
          return;
        }

        result.style.color = "#22c55e";
        result.textContent = t("setup.openai_auth_saved_success");
        result.classList.remove("hidden");
        await _loadConfig();
        await _loadChecklist();
        await _loadOpenAIAuthSettings();
      } catch {
        result.style.color = "#ef4444";
        result.textContent = t("setup.network_error");
        result.classList.remove("hidden");
      }
    });
  } catch {
    el.innerHTML = `<div class="loading-placeholder">${t("setup.openai_auth_fetch_failed")}</div>`;
  }
}
