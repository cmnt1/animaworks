// ── Scheduler Page ─────────────────────────
import { api } from "../modules/api.js";
import { escapeHtml, timeStr } from "../modules/state.js";
import { t } from "/shared/i18n.js";

let _refreshInterval = null;
const SCHEDULER_SORT_STORAGE_KEY = "animaworks-scheduler-sort";
const DEFAULT_SCHEDULER_SORT = "org";
const DEPARTMENT_ORDER = ["全社", "Administration", "Property", "Finance", "Affiliate"];
const TITLE_ORDER = ["COO", "グループリーダー", "アソシエイト"];
let _listSortKey = _loadListSortKey();
let _listFilterField = "";
let _listFilterValue = "";

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

    <div class="card">
      <div class="card-header">${t("server.scheduler_status")}</div>
      <div class="card-body" id="schedulerPageContent">
        <div class="loading-placeholder">${t("common.loading")}</div>
      </div>
    </div>
  `;

  _loadScheduler();
  _refreshInterval = setInterval(_loadScheduler, 30000);
}

export function destroy() {
  if (_refreshInterval) clearInterval(_refreshInterval);
  _refreshInterval = null;
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
