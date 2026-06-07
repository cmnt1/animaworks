import {
  createSnsSearchEntry,
  deleteSnsSearchEntry,
  fetchSnsSearchEntries,
  updateSnsSearchEntry,
} from "./api.js";
import { escapeHtml } from "./utils.js";

let rootEl = null;
let entries = [];
let busy = false;

export async function initSnsSearchPage(container) {
  rootEl = container;
  await loadEntries();
}

export function disposeSnsSearchPage() {
  rootEl = null;
  entries = [];
  busy = false;
}

async function loadEntries() {
  if (!rootEl) return;
  setBusy(true);
  try {
    const data = await fetchSnsSearchEntries();
    entries = Array.isArray(data.items) ? data.items : [];
    render();
  } catch (err) {
    renderError(err);
  } finally {
    setBusy(false);
  }
}

function setBusy(nextBusy) {
  busy = nextBusy;
  if (rootEl) rootEl.classList.toggle("is-busy", busy);
}

function divisions() {
  const values = new Set(["Finance"]);
  for (const entry of entries) {
    if (entry.Division) values.add(entry.Division);
  }
  return Array.from(values).sort((a, b) => a.localeCompare(b));
}

function render() {
  if (!rootEl) return;
  const divisionOptions = divisions()
    .map((division) => `<option value="${escapeHtml(division)}"></option>`)
    .join("");
  const rows = entries.map(renderRow).join("");

  rootEl.innerHTML = `
    <section class="ws-sns-page">
      <header class="ws-sns-header">
        <div>
          <p class="ws-sns-kicker">general_db / T_Sns_Search</p>
          <h1>SNS Search Words</h1>
        </div>
        <button type="button" class="ws-sns-secondary" data-action="reload">Reload</button>
      </header>

      <form class="ws-sns-form" data-action="create">
        <label>
          <span>Division</span>
          <input name="Division" list="wsSnsDivisions" value="Finance" autocomplete="off" required>
        </label>
        <label>
          <span>Words</span>
          <textarea name="Words" rows="3" placeholder="market OR stocks OR FX" required></textarea>
        </label>
        <button type="submit" class="ws-sns-primary">Add</button>
      </form>
      <datalist id="wsSnsDivisions">${divisionOptions}</datalist>

      <div class="ws-sns-table-wrap">
        <table class="ws-sns-table">
          <thead>
            <tr>
              <th>ID_Sns_Search</th>
              <th>Division</th>
              <th>Words</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            ${rows || `<tr><td colspan="4" class="ws-sns-empty">No search words yet.</td></tr>`}
          </tbody>
        </table>
      </div>
    </section>
  `;
  bindEvents();
}

function renderRow(entry) {
  const id = entry.ID_Sns_Search;
  return `
    <tr data-entry-id="${id}">
      <td class="ws-sns-id">${id}</td>
      <td>
        <input class="ws-sns-cell-input" name="Division" list="wsSnsDivisions" value="${escapeHtml(entry.Division)}">
      </td>
      <td>
        <textarea class="ws-sns-cell-words" name="Words" rows="2">${escapeHtml(entry.Words)}</textarea>
      </td>
      <td>
        <div class="ws-sns-actions">
          <button type="button" class="ws-sns-primary" data-action="save">Save</button>
          <button type="button" class="ws-sns-danger" data-action="delete">Delete</button>
        </div>
      </td>
    </tr>
  `;
}

function bindEvents() {
  if (!rootEl) return;

  rootEl.querySelector('[data-action="reload"]')?.addEventListener("click", () => {
    loadEntries();
  });

  rootEl.querySelector('[data-action="create"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const formData = new FormData(form);
    await createSnsSearchEntry({
      Division: String(formData.get("Division") || "").trim(),
      Words: String(formData.get("Words") || "").trim(),
    });
    form.reset();
    form.elements.Division.value = "Finance";
    await loadEntries();
  });

  for (const row of rootEl.querySelectorAll("tr[data-entry-id]")) {
    row.querySelector('[data-action="save"]')?.addEventListener("click", () => saveRow(row));
    row.querySelector('[data-action="delete"]')?.addEventListener("click", () => deleteRow(row));
  }
}

async function saveRow(row) {
  if (busy) return;
  const id = row.dataset.entryId;
  const division = row.querySelector('[name="Division"]')?.value.trim() || "";
  const words = row.querySelector('[name="Words"]')?.value.trim() || "";
  if (!division || !words) return;
  setBusy(true);
  try {
    await updateSnsSearchEntry(id, { Division: division, Words: words });
    await loadEntries();
  } finally {
    setBusy(false);
  }
}

async function deleteRow(row) {
  if (busy) return;
  const id = row.dataset.entryId;
  setBusy(true);
  try {
    await deleteSnsSearchEntry(id);
    await loadEntries();
  } finally {
    setBusy(false);
  }
}

function renderError(err) {
  if (!rootEl) return;
  rootEl.innerHTML = `
    <section class="ws-sns-page">
      <header class="ws-sns-header">
        <div>
          <p class="ws-sns-kicker">general_db / T_Sns_Search</p>
          <h1>SNS Search Words</h1>
        </div>
      </header>
      <div class="ws-sns-error">${escapeHtml(err?.message || "Failed to load search words.")}</div>
    </section>
  `;
}
