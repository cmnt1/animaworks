// ── Scheduler Page ─────────────────────────
import { api } from "../modules/api.js";
import { escapeHtml, timeStr } from "../modules/state.js";
import { onEvent } from "../modules/websocket.js";
import { t } from "/shared/i18n.js";

let _refreshInterval = null;
let _unsubConsolidation = null;
let _consolidationModels = [];
const _WEEKDAYS_JA = ["日", "月", "火", "水", "木", "金", "土"];
const SCHEDULER_SORT_STORAGE_KEY = "animaworks-scheduler-sort";
const DEFAULT_SCHEDULER_SORT = "org";
const DEPARTMENT_ORDER = ["全社", "Administration", "Property", "Finance", "Affiliate"];
const TITLE_ORDER = ["COO", "グループリーダー", "アソシエイト"];
let _listSortKey = _loadListSortKey();
let _listFilterField = "";
let _listFilterValue = "";

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

export function consolidationProgressText(job) {
  if (!job?.running) return "";
  const current = Number(job.progress_current) || 0;
  const total = Number(job.progress_total) || 0;
  if (current < 1 || total < 1) return "";
  return `${Math.min(current, total)}/${total}`;
}

function _loadListSortKey() {
  try {
    return localStorage.getItem(SCHEDULER_SORT_STORAGE_KEY) || DEFAULT_SCHEDULER_SORT;
  } catch {
    return DEFAULT_SCHEDULER_SORT;
  }
}

function _saveListSortKey(value) {
  _listSortKey = value || DEFAULT_SCHEDULER_SORT;
  try {
    localStorage.setItem(SCHEDULER_SORT_STORAGE_KEY, _listSortKey);
  } catch {
    // Keep the in-memory value even when storage is unavailable.
  }
}

function _sortRank(value, order) {
  const text = String(value || "").trim();
  if (!text) return order.length + 1;
  const exact = order.indexOf(text);
  if (exact >= 0) return exact;
  const lower = text.toLowerCase();
  const lowerIdx = order.findIndex(item => item.toLowerCase() === lower);
  return lowerIdx >= 0 ? lowerIdx : order.length;
}

function _compareText(a, b) {
  return String(a || "").localeCompare(String(b || ""), "ja", { numeric: true, sensitivity: "base" });
}

function _compareNumber(a, b) {
  const av = Number.isFinite(a) ? a : Number.POSITIVE_INFINITY;
  const bv = Number.isFinite(b) ? b : Number.POSITIVE_INFINITY;
  return av - bv;
}

function _padTimePart(value) {
  return String(value).padStart(2, "0");
}

function _formatCronTime(minute, hour) {
  if (/^\d+$/.test(minute) && /^\d+$/.test(hour)) {
    return `${_padTimePart(hour)}:${_padTimePart(minute)}`;
  }
  if (/^\d+$/.test(minute) && hour.includes(",")) {
    return hour
      .split(",")
      .filter(Boolean)
      .map(h => `${_padTimePart(h)}:${_padTimePart(minute)}`)
      .join("、");
  }
  if (hour === "*" && /^\d+$/.test(minute)) return `毎時 ${_padTimePart(minute)}分`;
  if (minute.startsWith("*/") && hour === "*") return `${minute.slice(2)}分ごと`;
  return `${minute}分 ${hour}時`;
}

function _formatCronWeekdays(dow) {
  const names = ["日", "月", "火", "水", "木", "金", "土"];
  const aliases = { sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6 };
  if (!dow || dow === "*") return "";
  const normalized = dow.toLowerCase();
  if (aliases[normalized] !== undefined) return `毎週${names[aliases[normalized]]}`;
  if (/^[a-z]{3}-[a-z]{3}$/i.test(dow)) {
    const [startName, endName] = normalized.split("-");
    const start = aliases[startName];
    const end = aliases[endName];
    if (start !== undefined && end !== undefined) {
      if (start === 1 && end === 5) return "平日";
      return `毎週${names[start]}〜${names[end]}`;
    }
  }
  if (/^\d-\d$/.test(dow)) {
    const [start, end] = dow.split("-").map(Number);
    if (start === 1 && end === 5) return "平日";
    if (start >= 0 && end <= 6 && start <= end) return `毎週${names[start]}〜${names[end]}`;
  }
  if (/^\d(,\d)*$/.test(dow)) {
    return `毎週${dow.split(",").map(v => names[Number(v)] || v).join("・")}`;
  }
  if (/^\d$/.test(dow)) return `毎週${names[Number(dow)] || dow}`;
  return `曜日 ${dow}`;
}

function _formatFiveFieldCron(expr) {
  const parts = String(expr || "").trim().split(/\s+/);
  if (parts.length !== 5) return "";
  const [minute, hour, day, month, dow] = parts;
  const time = _formatCronTime(minute, hour);
  if (day === "*" && month === "*" && dow === "*") return `毎日 ${time}`;
  if (day === "*" && month === "*" && dow !== "*") return `${_formatCronWeekdays(dow)} ${time}`;
  if (day !== "*" && month === "*" && dow === "*") return `毎月${day}日 ${time}`;
  if (day !== "*" && month !== "*" && dow === "*") return `毎年${month}月${day}日 ${time}`;
  return `${time}（条件: 日=${day} 月=${month} 曜日=${dow}）`;
}

function _formatCronTrigger(trigger) {
  const text = String(trigger || "");
  if (!text.startsWith("cron[")) return "";
  const hour = text.match(/hour='([^']+)'/)?.[1] || "*";
  const minute = text.match(/minute='([^']+)'/)?.[1] || "0";
  const day = text.match(/day='([^']+)'/)?.[1] || "*";
  const month = text.match(/month='([^']+)'/)?.[1] || "*";
  const dow = text.match(/day_of_week='([^']+)'/)?.[1] || "*";
  return _formatFiveFieldCron(`${minute} ${hour} ${day} ${month} ${dow}`);
}

function _formatScheduleForHuman(job) {
  const raw = String(job?.schedule || job?.trigger || "").trim();
  if (!raw) return "--";
  const cronLabel = _formatFiveFieldCron(raw);
  if (cronLabel) return cronLabel;
  const triggerLabel = _formatCronTrigger(raw);
  if (triggerLabel) return triggerLabel;
  if (raw.includes("`") || raw.split(/\s+/).length > 5) return "未設定または無効なスケジュール";
  return raw;
}

function _displayRole(role) {
  if (!role) return "--";
  const key = `tb.role.${role}`;
  const label = t(key);
  return label === key ? role : label;
}

function _metadataByName(animas) {
  const byName = new Map();
  for (const anima of Array.isArray(animas) ? animas : []) {
    if (anima?.name) byName.set(anima.name, anima);
  }
  byName.set("system", {
    name: "system",
    department: "全社",
    title: "システム",
    role: "基盤運用",
  });
  return byName;
}

function _jobPerson(job, byName) {
  return byName.get(job?.anima) || {
    name: job?.anima || "--",
    department: "--",
    title: "--",
    role: "--",
  };
}

function _jobRow(job, byName) {
  const person = _jobPerson(job, byName);
  return {
    job,
    jobRef: job?.id || "",
    person,
    department: person.department || "",
    title: person.title || "",
    role: person.role || "",
    name: person.name || job?.anima || "",
    jobName: job?.name || job?.id || "",
    scheduleLabel: _formatScheduleForHuman(job),
    lastRun: job?.last_run || "",
    nextRun: job?.next_run || "",
  };
}

function _copyTextWithSelection(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  textarea.setSelectionRange(0, text.length);
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  }
  textarea.remove();
  return copied;
}

function _copyText(text) {
  if (_copyTextWithSelection(text)) return Promise.resolve();
  if (!navigator.clipboard?.writeText) return Promise.reject(new Error("clipboard unavailable"));
  return Promise.race([
    navigator.clipboard.writeText(text),
    new Promise((_, reject) => setTimeout(() => reject(new Error("clipboard timeout")), 800)),
  ]);
}

function _jobReferenceText(row) {
  return `ジョブ番号: ${row.jobRef || "--"}\nジョブ名: ${row.jobName || "--"}`;
}

function _filterFieldValue(row, field) {
  switch (field) {
    case "department":
      return row.department || "";
    case "role":
      return row.role || "";
    case "title":
      return row.title || "";
    case "name":
      return row.name || "";
    default:
      return "";
  }
}

function _filterDisplayValue(value, field) {
  if (!value) return t("animas.not_set");
  if (field === "role") return _displayRole(value);
  return value;
}

function _uniqueFilterValues(rows, field) {
  if (!field) return [];
  return [...new Set(rows.map(row => _filterFieldValue(row, field)).filter(Boolean))]
    .sort((a, b) => {
      if (field === "department") {
        return _compareNumber(_sortRank(a, DEPARTMENT_ORDER), _sortRank(b, DEPARTMENT_ORDER)) || _compareText(a, b);
      }
      if (field === "title") {
        return _compareNumber(_sortRank(a, TITLE_ORDER), _sortRank(b, TITLE_ORDER)) || _compareText(a, b);
      }
      return _compareText(_filterDisplayValue(a, field), _filterDisplayValue(b, field));
    });
}

function _filterFieldOptionHtml(value, labelKey) {
  const selected = _listFilterField === value ? " selected" : "";
  return `<option value="${escapeHtml(value)}"${selected}>${escapeHtml(t(labelKey))}</option>`;
}

function _filterValueOptionsHtml(rows) {
  const values = _uniqueFilterValues(rows, _listFilterField);
  const allSelected = !_listFilterValue ? " selected" : "";
  return `
    <option value=""${allSelected}>${escapeHtml(t("animas.filter_value_all"))}</option>
    ${values.map(value => {
      const selected = _listFilterValue === value ? " selected" : "";
      return `<option value="${escapeHtml(value)}"${selected}>${escapeHtml(_filterDisplayValue(value, _listFilterField))}</option>`;
    }).join("")}
  `;
}

function _filterRows(rows) {
  if (!_listFilterField || !_listFilterValue) return rows;
  return rows.filter(row => _filterFieldValue(row, _listFilterField) === _listFilterValue);
}

function _sortRows(rows) {
  const sorted = [...rows];
  const byName = (a, b) => _compareText(a.name, b.name);
  const byDepartment = (a, b) =>
    _compareNumber(_sortRank(a.department, DEPARTMENT_ORDER), _sortRank(b.department, DEPARTMENT_ORDER)) ||
    _compareText(a.department, b.department);
  const byTitle = (a, b) =>
    _compareNumber(_sortRank(a.title, TITLE_ORDER), _sortRank(b.title, TITLE_ORDER)) ||
    _compareText(a.title, b.title);
  const byRole = (a, b) => _compareText(_displayRole(a.role), _displayRole(b.role));

  sorted.sort((a, b) => {
    switch (_listSortKey) {
      case "department":
        return byDepartment(a, b) || byName(a, b) || _compareText(a.jobName, b.jobName);
      case "role":
        return byRole(a, b) || byDepartment(a, b) || byTitle(a, b) || byName(a, b);
      case "title":
        return byTitle(a, b) || byDepartment(a, b) || byName(a, b);
      case "name":
        return byName(a, b) || _compareText(a.jobName, b.jobName);
      case "job_name":
        return _compareText(a.jobName, b.jobName) || byName(a, b);
      case "schedule":
        return _compareText(a.scheduleLabel, b.scheduleLabel) || byDepartment(a, b) || byName(a, b);
      case "last_run":
        return _compareText(a.lastRun, b.lastRun) || byDepartment(a, b) || byName(a, b);
      case "next_run":
        return _compareText(a.nextRun, b.nextRun) || byDepartment(a, b) || byName(a, b);
      case "org":
      default:
        return byDepartment(a, b) || byTitle(a, b) || byRole(a, b) || byName(a, b) || _compareText(a.jobName, b.jobName);
    }
  });
  return sorted;
}

function _sortOptionHtml(value, labelKey) {
  const selected = _listSortKey === value ? " selected" : "";
  return `<option value="${escapeHtml(value)}"${selected}>${escapeHtml(t(labelKey))}</option>`;
}

export function render(container) {
  container.innerHTML = `
    <div class="page-header">
      <h2>${t("nav.scheduler")}</h2>
    </div>

    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">${t("server.memory_maintenance")}</div>
      <div class="card-body">
        <div id="serverConsolidationModel">
          <div class="loading-placeholder">${t("common.loading")}</div>
        </div>
        <div id="serverConsolidationContent">
          <div class="loading-placeholder">${t("common.loading")}</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">${t("server.scheduler")}</div>
      <div class="card-body" id="schedulerPageContent">
        <div class="loading-placeholder">${t("common.loading")}</div>
      </div>
    </div>
  `;

  _loadConsolidationModel();
  _loadConsolidation();
  _loadScheduler();
  _refreshInterval = setInterval(() => {
    _loadConsolidation();
    _loadScheduler();
  }, 30000);
  _unsubConsolidation = onEvent("system.consolidation_status", _renderConsolidationData);
}

export function destroy() {
  if (_refreshInterval) clearInterval(_refreshInterval);
  _refreshInterval = null;
  if (_unsubConsolidation) {
    _unsubConsolidation();
    _unsubConsolidation = null;
  }
}

const _CONSOLIDATION_JOBS = [
  { key: "daily", labelKey: "server.consolidation_daily" },
  { key: "weekly", labelKey: "server.consolidation_weekly" },
  { key: "monthly", labelKey: "server.consolidation_monthly" },
];

function _modelMetaFromId(modelId, option = {}) {
  const id = String(modelId || option.id || "");
  const explicitRoute = String(option.route || option.execution_mode || "").toUpperCase();
  const explicitProvider = option.provider || "";
  const explicitModelName = option.model_name || "";

  if (explicitRoute && explicitProvider && explicitModelName) {
    return { route: explicitRoute, provider: explicitProvider, modelName: explicitModelName };
  }
  if (id.startsWith("claude-")) {
    return { route: explicitRoute || "S", provider: explicitProvider || "Anthropic", modelName: explicitModelName || id };
  }
  if (id.startsWith("anthropic/claude-")) {
    return { route: explicitRoute || "A", provider: explicitProvider || "Anthropic", modelName: explicitModelName || id.replace(/^anthropic\//, "") };
  }
  if (id.startsWith("codex/") || id.startsWith("openai-codex/")) {
    return { route: explicitRoute || "C", provider: explicitProvider || "OpenAI", modelName: explicitModelName || id.replace(/^openai-codex\//, "") };
  }
  if (id.startsWith("grok/")) {
    return { route: explicitRoute || "C", provider: explicitProvider || "Grok", modelName: explicitModelName || id.replace(/^grok\//, "") };
  }
  if (id.startsWith("openai/")) {
    return { route: explicitRoute || "A", provider: explicitProvider || "OpenAI", modelName: explicitModelName || id.replace(/^openai\//, "") };
  }
  if (/^(gpt-|o3|o4-)/.test(id)) {
    return { route: explicitRoute || "A", provider: explicitProvider || "OpenAI", modelName: explicitModelName || id };
  }
  if (id.startsWith("google/")) {
    return { route: explicitRoute || "A", provider: explicitProvider || "Google", modelName: explicitModelName || id.replace(/^google\//, "") };
  }
  if (id.startsWith("nanogpt/")) {
    return { route: explicitRoute || "A", provider: explicitProvider || "nanoGPT", modelName: explicitModelName || id.replace(/^nanogpt\//, "") };
  }
  if (id.startsWith("ollama/")) {
    return { route: explicitRoute || "B", provider: explicitProvider || "Ollama", modelName: explicitModelName || id.replace(/^ollama\//, "") };
  }
  return { route: explicitRoute || "A", provider: explicitProvider || "Custom", modelName: explicitModelName || id };
}

function _normaliseConsolidationModels(models, currentModel, currentCredential) {
  const list = (models || []).map(option => {
    const meta = _modelMetaFromId(option.id, option);
    return {
      ...option,
      route: meta.route,
      provider: meta.provider,
      model_name: meta.modelName,
      credential: option.id === currentModel && currentCredential
        ? currentCredential
        : (option.credential || ""),
    };
  });
  if (currentModel && !list.some(option => option.id === currentModel)) {
    const meta = _modelMetaFromId(currentModel);
    list.push({
      id: currentModel,
      route: meta.route,
      provider: meta.provider,
      model_name: meta.modelName,
      credential: currentCredential || "",
    });
  }
  return list;
}

function _uniqueSorted(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) =>
    String(a).localeCompare(String(b), "ja", { numeric: true, sensitivity: "base" }),
  );
}

function _uniqueRoutes(values) {
  const order = ["S", "C", "A", "B"];
  return [...new Set(values.filter(Boolean))].sort((a, b) => {
    const ai = order.includes(a) ? order.indexOf(a) : order.length;
    const bi = order.includes(b) ? order.indexOf(b) : order.length;
    return ai - bi || String(a).localeCompare(String(b));
  });
}

function _selectOptionsHtml(values, selectedValue, placeholder) {
  return `
    <option value=""${selectedValue ? "" : " selected"}>${escapeHtml(placeholder)}</option>
    ${values.map(value => {
      const selected = value === selectedValue ? " selected" : "";
      return `<option value="${escapeHtml(value)}"${selected}>${escapeHtml(value)}</option>`;
    }).join("")}
  `;
}

function _consolidationModelPickerHtml(models, currentModel, currentCredential) {
  const list = _normaliseConsolidationModels(models, currentModel, currentCredential);
  const selected = list.find(option => option.id === currentModel) || list[0] || null;
  const selectedRoute = selected?.route || "";
  const selectedProvider = selected?.provider || "";
  const routes = _uniqueRoutes(list.map(option => option.route));
  const providers = _uniqueSorted(list.filter(option => option.route === selectedRoute).map(option => option.provider));
  const modelOptions = list.filter(option => option.route === selectedRoute && option.provider === selectedProvider);

  return `
    <div class="model-picker" style="flex:1; min-width:0; display:grid; grid-template-columns:minmax(110px,0.7fr) minmax(135px,0.8fr) minmax(220px,1.5fr); gap:0.5rem;">
      <select id="consolidationRouteSelect" style="min-width:0; padding:0.4rem 0.5rem; border:1px solid var(--border,#ddd); border-radius:4px; font-size:0.85rem; background:var(--bg-secondary,#fff); color:var(--text-primary,#333);">
        ${_selectOptionsHtml(routes, selectedRoute, t("animas.model_route"))}
      </select>
      <select id="consolidationProviderSelect" style="min-width:0; padding:0.4rem 0.5rem; border:1px solid var(--border,#ddd); border-radius:4px; font-size:0.85rem; background:var(--bg-secondary,#fff); color:var(--text-primary,#333);">
        ${_selectOptionsHtml(providers, selectedProvider, t("animas.model_provider"))}
      </select>
      <select id="consolidationModelSelect" style="min-width:0; padding:0.4rem 0.5rem; border:1px solid var(--border,#ddd); border-radius:4px; font-size:0.85rem; background:var(--bg-secondary,#fff); color:var(--text-primary,#333);">
        ${modelOptions.map(option => {
          const selectedAttr = option.id === selected?.id ? " selected" : "";
          return `<option value="${escapeHtml(option.id)}" data-credential="${escapeHtml(option.credential || "")}"${selectedAttr}>${escapeHtml(option.model_name)}</option>`;
        }).join("")}
      </select>
    </div>
  `;
}

function _bindConsolidationModelPicker(models, currentModel, currentCredential) {
  const routeSelect = document.getElementById("consolidationRouteSelect");
  const providerSelect = document.getElementById("consolidationProviderSelect");
  const modelSelect = document.getElementById("consolidationModelSelect");
  if (!routeSelect || !providerSelect || !modelSelect) return;

  const list = _normaliseConsolidationModels(models, currentModel, currentCredential);
  const setModels = (route, provider, selectedModel = "") => {
    const options = list.filter(option => option.route === route && option.provider === provider);
    modelSelect.innerHTML = options.map(option => {
      const selected = option.id === selectedModel ? " selected" : "";
      return `<option value="${escapeHtml(option.id)}" data-credential="${escapeHtml(option.credential || "")}"${selected}>${escapeHtml(option.model_name)}</option>`;
    }).join("");
    modelSelect.disabled = options.length === 0;
  };
  const setProviders = (selectedProvider = "", selectedModel = "") => {
    const providers = _uniqueSorted(list.filter(option => option.route === routeSelect.value).map(option => option.provider));
    const provider = providers.includes(selectedProvider) ? selectedProvider : (providers[0] || "");
    providerSelect.innerHTML = _selectOptionsHtml(providers, provider, t("animas.model_provider"));
    providerSelect.disabled = providers.length === 0;
    setModels(routeSelect.value, provider, selectedModel);
  };

  routeSelect.addEventListener("change", () => setProviders());
  providerSelect.addEventListener("change", () => setModels(routeSelect.value, providerSelect.value));
}

const _MODEL_REFRESH_PROVIDER_LABELS = {
  claude_code: "Claude Code",
  codex: "Codex",
  nanogpt: "nanoGPT",
  google: "Google",
};

function _modelRefreshSourceLabel(result) {
  const source = result?.source || "";
  const status = result?.status || "";
  if (source === "known" || status === "fallback") return t("animas.model_refresh_source_known");
  if (source === "cache" || status === "cached") return t("animas.model_refresh_source_cache");
  if (source === "none" || status === "skipped") return t("animas.model_refresh_source_none");
  if (status === "error") return t("animas.model_refresh_source_error");
  return status || t("animas.model_refresh_source_unknown");
}

function _modelRefreshStatusInfo(results) {
  const nonDynamic = (Array.isArray(results) ? results : []).filter(result => result && result.dynamic !== true);
  if (nonDynamic.length === 0) {
    return {
      text: t("animas.model_refreshed"),
      color: "var(--color-success, #28a745)",
      title: "",
      transient: true,
    };
  }

  const providerLabel = provider => _MODEL_REFRESH_PROVIDER_LABELS[provider] || provider || "";
  const providers = nonDynamic
    .map(result => `${providerLabel(result.provider)}: ${_modelRefreshSourceLabel(result)}`)
    .join(", ");
  const details = nonDynamic
    .map(result => {
      const detail = `${providerLabel(result.provider)}: ${_modelRefreshSourceLabel(result)}`;
      return result.message ? `${detail} - ${result.message}` : detail;
    })
    .join("\n");
  return {
    text: t("animas.model_refresh_non_dynamic", { providers }),
    color: "var(--color-warning, #e8a000)",
    title: details,
    transient: false,
  };
}

function _replaceConsolidationModelPicker(models, currentModel, currentCredential) {
  const picker = document.querySelector("#serverConsolidationModel .model-picker");
  if (!picker) return;
  picker.outerHTML = _consolidationModelPickerHtml(models, currentModel, currentCredential);
  _bindConsolidationModelPicker(models, currentModel, currentCredential);
}

async function _refreshConsolidationModels() {
  const btn = document.getElementById("consolidationModelRefreshBtn");
  const saveBtn = document.getElementById("consolidationModelSaveBtn");
  const status = document.getElementById("consolidationModelStatus");
  const modelSelect = document.getElementById("consolidationModelSelect");
  if (!btn || !status) return;

  const selectedOption = modelSelect?.options[modelSelect.selectedIndex];
  const currentModel = modelSelect?.value || "";
  const currentCredential = selectedOption?.dataset?.credential || "";
  btn.disabled = true;
  if (saveBtn) saveBtn.disabled = true;
  btn.textContent = t("animas.model_refreshing");
  status.textContent = "";
  status.removeAttribute("title");

  try {
    const result = await api("/api/system/available-models/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ providers: ["claude_code", "codex", "nanogpt", "google"] }),
    });
    if (Array.isArray(result.models)) {
      _consolidationModels = result.models;
    } else {
      const modelsData = await api("/api/system/available-models");
      _consolidationModels = modelsData.models || [];
    }
    _replaceConsolidationModelPicker(_consolidationModels, currentModel, currentCredential);

    const info = _modelRefreshStatusInfo(result.providers);
    status.textContent = info.text;
    status.style.color = info.color;
    if (info.title) status.title = info.title;
    if (info.transient) {
      setTimeout(() => {
        status.textContent = "";
        status.removeAttribute("title");
      }, 5000);
    }
  } catch (err) {
    status.textContent = t("animas.model_refresh_failed");
    status.style.color = "var(--color-danger, #dc3545)";
    status.removeAttribute("title");
    console.error("Consolidation model refresh failed:", err);
  } finally {
    btn.disabled = false;
    if (saveBtn) saveBtn.disabled = false;
    btn.textContent = t("animas.model_refresh");
  }
}

async function _loadConsolidationModel() {
  const content = document.getElementById("serverConsolidationModel");
  if (!content) return;
  try {
    const [config, modelsData] = await Promise.all([
      api("/api/system/config"),
      api("/api/system/available-models"),
    ]);
    _consolidationModels = modelsData.models || [];
    const consolidation = config.consolidation || {};
    content.innerHTML = `
      <div style="display:flex; align-items:center; gap:0.75rem; flex-wrap:wrap; padding-bottom:1rem; margin-bottom:1rem; border-bottom:1px solid var(--border,#ddd);">
        <label style="font-weight:600; font-size:0.9rem; min-width:160px; flex-shrink:0;">${t("server.consolidation_model")}:</label>
        ${_consolidationModelPickerHtml(_consolidationModels, consolidation.llm_model, consolidation.llm_credential)}
        <button class="btn-primary" id="consolidationModelSaveBtn" style="font-size:0.85rem; padding:0.4rem 0.75rem;">${t("server.consolidation_model_save")}</button>
        <button class="btn-secondary" id="consolidationModelRefreshBtn" style="font-size:0.85rem; padding:0.4rem 0.75rem;">${t("animas.model_refresh")}</button>
        <span id="consolidationModelStatus" style="font-size:0.75rem; color:var(--text-secondary,#888);"></span>
        <div style="flex-basis:100%; margin-left:172px; font-size:0.75rem; color:var(--text-secondary,#888);">${t("server.consolidation_model_hint")}</div>
      </div>
    `;
    _bindConsolidationModelPicker(_consolidationModels, consolidation.llm_model, consolidation.llm_credential);
    document.getElementById("consolidationModelSaveBtn")?.addEventListener("click", _saveConsolidationModel);
    document.getElementById("consolidationModelRefreshBtn")?.addEventListener("click", _refreshConsolidationModels);
  } catch (err) {
    content.innerHTML = `<div class="loading-placeholder">${escapeHtml(t("server.consolidation_model_load_failed"))}</div>`;
    console.error("Consolidation model load failed:", err);
  }
}

async function _saveConsolidationModel() {
  const btn = document.getElementById("consolidationModelSaveBtn");
  const status = document.getElementById("consolidationModelStatus");
  const modelSelect = document.getElementById("consolidationModelSelect");
  if (!btn || !status || !modelSelect?.value) return;
  const option = modelSelect.options[modelSelect.selectedIndex];
  const model = modelSelect.value;
  const credential = option?.dataset?.credential || "";

  btn.disabled = true;
  status.textContent = t("server.consolidation_model_saving");
  status.style.color = "var(--text-secondary,#888)";
  try {
    await api("/api/system/consolidation/model", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, credential }),
    });
    status.textContent = t("server.consolidation_model_saved");
    status.style.color = "var(--aw-color-success,#38a169)";
  } catch (err) {
    status.textContent = t("server.consolidation_model_save_failed");
    status.style.color = "var(--aw-color-danger,#e53e3e)";
    console.error("Consolidation model save failed:", err);
  } finally {
    btn.disabled = false;
  }
}

async function _loadConsolidation() {
  const content = document.getElementById("serverConsolidationContent");
  if (!content) return;
  try {
    _renderConsolidationData(await api("/api/system/consolidation/status"));
  } catch {
    content.innerHTML = `<div class="loading-placeholder">${t("server.api_unimplemented")}</div>`;
  }
}

function _renderConsolidationData(data) {
  const content = document.getElementById("serverConsolidationContent");
  if (!content) return;

  const rows = _CONSOLIDATION_JOBS.map(({ key, labelKey }) => {
    const job = data?.[key] || {};
    const status = job.running ? "running" : (job.missed ? "missed" : (job.last_status || "never"));
    const errorText = job.last_error ? escapeHtml(job.last_error) : "";
    const progressText = consolidationProgressText(job);
    const phaseKey = job.progress_phase
      ? `server.consolidation_phase_${job.progress_phase}`
      : "";
    const phaseText = phaseKey && t(phaseKey) !== phaseKey ? t(phaseKey) : "";
    const progressDetail = [job.progress_target, phaseText].filter(Boolean).join(" · ");
    return `
      <tr>
        <td style="font-weight:500;">${t(labelKey)}</td>
        <td>
          <div style="display:flex;align-items:center;gap:0.4rem;">
            ${_consolidationStatusBadge(status)}
            ${progressText ? `<strong>${escapeHtml(progressText)}</strong>` : ""}
          </div>
          ${progressDetail ? `<div style="margin-top:0.2rem;font-size:0.78rem;color:var(--text-secondary,#666);">${escapeHtml(progressDetail)}</div>` : ""}
        </td>
        <td>${escapeHtml(_consolidationTimeStr(job.last_success_at))}</td>
        <td style="color:var(--aw-color-danger,#e53e3e);font-size:0.85em;">${errorText}</td>
        <td>
          <button class="btn btn-sm btn-outline" data-consolidation-run="${key}" ${job.running ? "disabled" : ""}>
            ${t("server.consolidation_run")}
          </button>
        </td>
      </tr>
    `;
  }).join("");
  const anyRunning = _CONSOLIDATION_JOBS.some(({ key }) => data?.[key]?.running);

  content.innerHTML = `
    <div class="data-table-wrapper">
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
    </div>
    <div style="margin-top: 0.75rem; text-align: right;">
      <button class="btn btn-sm btn-outline" id="consolidationCatchupBtn" ${anyRunning ? "disabled" : ""}>
        ${t("server.consolidation_catchup")}
      </button>
    </div>
  `;

  content.querySelectorAll("[data-consolidation-run]").forEach(btn => {
    btn.addEventListener("click", () => _runConsolidation(btn.dataset.consolidationRun));
  });
  document.getElementById("consolidationCatchupBtn")?.addEventListener("click", _runConsolidationCatchup);
}

function _consolidationStatusBadge(status) {
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
  const btn = document.querySelector(`[data-consolidation-run="${jobType}"]`);
  if (btn) btn.disabled = true;
  try {
    await api(`/api/system/consolidation/${jobType}/run`, { method: "POST" });
    setTimeout(_loadConsolidation, 100);
  } catch (err) {
    if (btn) btn.disabled = false;
    console.error("Consolidation run failed:", err);
  }
}

async function _runConsolidationCatchup() {
  const btn = document.getElementById("consolidationCatchupBtn");
  if (btn) btn.disabled = true;
  try {
    await api("/api/system/consolidation/catchup", { method: "POST" });
    setTimeout(_loadConsolidation, 100);
  } catch (err) {
    if (btn) btn.disabled = false;
    console.error("Consolidation catch-up failed:", err);
  }
}

async function _loadScheduler() {
  const content = document.getElementById("schedulerPageContent");
  if (!content) return;

  try {
    const [data, animas] = await Promise.all([
      api("/api/system/scheduler"),
      api("/api/animas").catch(() => []),
    ]);
    const people = _metadataByName(animas);
    const jobs = Array.isArray(data.jobs)
      ? data.jobs
      : [
          ...(Array.isArray(data.system_jobs) ? data.system_jobs : []),
          ...(Array.isArray(data.anima_jobs) ? data.anima_jobs : []),
        ];
    const allRows = jobs.map(job => _jobRow(job, people));

    if (allRows.length === 0) {
      content.innerHTML = `<div class="loading-placeholder">${t("server.no_jobs")}</div>`;
      return;
    }

    if (
      _listFilterField &&
      _listFilterValue &&
      !_uniqueFilterValues(allRows, _listFilterField).includes(_listFilterValue)
    ) {
      _listFilterValue = "";
    }

    const rows = _sortRows(_filterRows(allRows));
    content.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; gap:0.75rem; flex-wrap:wrap; margin-bottom:0.75rem;">
        <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
          <label for="schedulerFilterFieldSelect" style="font-size:0.85rem; color:var(--text-secondary,#666);">${t("animas.filter_label")}</label>
          <select id="schedulerFilterFieldSelect" style="min-width:150px; padding:0.35rem 0.5rem; border:1px solid var(--border,#ddd); border-radius:4px; background:var(--bg-secondary,#fff); color:var(--text-primary,#333); font-size:0.85rem;">
            ${_filterFieldOptionHtml("", "animas.filter_none")}
            ${_filterFieldOptionHtml("department", "animas.table_department")}
            ${_filterFieldOptionHtml("role", "animas.table_role")}
            ${_filterFieldOptionHtml("title", "animas.table_title")}
            ${_filterFieldOptionHtml("name", "animas.table_name")}
          </select>
          <select id="schedulerFilterValueSelect" ${_listFilterField ? "" : "disabled"} style="min-width:220px; padding:0.35rem 0.5rem; border:1px solid var(--border,#ddd); border-radius:4px; background:var(--bg-secondary,#fff); color:var(--text-primary,#333); font-size:0.85rem;">
            ${_filterValueOptionsHtml(allRows)}
          </select>
        </div>
        <div style="display:flex; align-items:center; gap:0.5rem;">
          <label for="schedulerSortSelect" style="font-size:0.85rem; color:var(--text-secondary,#666);">${t("animas.sort_label")}</label>
          <select id="schedulerSortSelect" style="min-width:220px; padding:0.35rem 0.5rem; border:1px solid var(--border,#ddd); border-radius:4px; background:var(--bg-secondary,#fff); color:var(--text-primary,#333); font-size:0.85rem;">
            ${_sortOptionHtml("org", "animas.sort_org")}
            ${_sortOptionHtml("department", "animas.table_department")}
            ${_sortOptionHtml("role", "animas.table_role")}
            ${_sortOptionHtml("title", "animas.table_title")}
            ${_sortOptionHtml("name", "animas.table_name")}
            ${_sortOptionHtml("job_name", "server.job_name")}
            ${_sortOptionHtml("schedule", "server.job_schedule")}
            ${_sortOptionHtml("last_run", "server.job_last_run")}
            ${_sortOptionHtml("next_run", "server.job_next_run")}
          </select>
        </div>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>${t("animas.table_department")}</th>
            <th>${t("animas.table_title")}</th>
            <th>${t("animas.table_role")}</th>
            <th>${t("animas.table_name")}</th>
            <th>ジョブ番号</th>
            <th>${t("server.job_name")}</th>
            <th>${t("server.job_schedule")}</th>
            <th>${t("server.job_last_run")}</th>
            <th>${t("server.job_next_run")}</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(row => {
            const { job: j, person } = row;
            return `
              <tr>
                <td>${escapeHtml(person.department || "--")}</td>
                <td>${escapeHtml(person.title || "--")}</td>
                <td>${escapeHtml(_displayRole(person.role))}</td>
                <td>${escapeHtml(person.name || j.anima || "--")}</td>
                <td>
                  <button
                    type="button"
                    class="scheduler-copy-job-btn"
                    data-job-ref="${escapeHtml(row.jobRef || "")}"
                    data-job-name="${escapeHtml(row.jobName || "")}"
                    title="ジョブ番号とジョブ名をコピー"
                    style="border:1px solid var(--aw-color-border); border-radius:999px; background:var(--aw-color-bg-secondary); color:var(--aw-color-text-muted); font-size:0.78rem; padding:0.15rem 0.5rem; cursor:pointer;"
                  ><code>${escapeHtml(row.jobRef || "--")}</code></button>
                </td>
                <td style="font-weight:500;">${escapeHtml(j.name || j.id || "--")}</td>
                <td title="${escapeHtml(j.schedule || j.trigger || "")}">${escapeHtml(row.scheduleLabel)}</td>
                <td>${escapeHtml(j.last_run ? timeStr(j.last_run) : "--")}</td>
                <td>${escapeHtml(j.next_run ? timeStr(j.next_run) : "--")}</td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    `;

    document.getElementById("schedulerSortSelect")?.addEventListener("change", (e) => {
      _saveListSortKey(e.target.value);
      _loadScheduler();
    });

    document.getElementById("schedulerFilterFieldSelect")?.addEventListener("change", (e) => {
      _listFilterField = e.target.value;
      _listFilterValue = "";
      _loadScheduler();
    });

    document.getElementById("schedulerFilterValueSelect")?.addEventListener("change", (e) => {
      _listFilterValue = e.target.value;
      _loadScheduler();
    });

    content.querySelectorAll(".scheduler-copy-job-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const row = {
          jobRef: btn.dataset.jobRef || "",
          jobName: btn.dataset.jobName || "",
        };
        const original = btn.textContent;
        btn.textContent = "コピー中...";
        try {
          await _copyText(_jobReferenceText(row));
          btn.textContent = "コピー済み";
          setTimeout(() => {
            if (btn.isConnected) btn.textContent = original;
          }, 1200);
        } catch {
          btn.textContent = "コピー失敗";
          setTimeout(() => {
            if (btn.isConnected) btn.textContent = original;
          }, 1200);
        }
      });
    });
  } catch {
    content.innerHTML = `<div class="loading-placeholder">${t("server.api_unimplemented")}</div>`;
  }
}
