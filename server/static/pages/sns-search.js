import { api } from "../modules/api.js";
import { escapeHtml } from "../modules/state.js";

let _items = [];

export function render(container) {
  container.innerHTML = `
    <div class="page-header">
      <h2>SNS Search Words</h2>
    </div>
    <section class="sns-search-panel">
      <form class="sns-search-form" id="snsSearchForm">
        <label class="sns-search-field">
          <span>Division</span>
          <input id="snsDivisionInput" name="Division" list="snsDivisionList" autocomplete="off" value="Finance">
          <datalist id="snsDivisionList"></datalist>
        </label>
        <label class="sns-search-field sns-search-field--wide">
          <span>Words</span>
          <textarea id="snsWordsInput" name="Words" rows="2" placeholder="$NVDA OR NVIDIA"></textarea>
        </label>
        <button type="submit" class="btn-primary sns-search-add">Add</button>
      </form>
    </section>
    <section class="sns-search-table-wrap">
      <div class="sns-search-status" id="snsSearchStatus">Loading...</div>
      <table class="data-table sns-search-table" id="snsSearchTable" hidden>
        <thead>
          <tr>
            <th class="sns-search-id-col">ID_Sns_Search</th>
            <th>Division</th>
            <th>Words</th>
            <th class="sns-search-action-col">Actions</th>
          </tr>
        </thead>
        <tbody id="snsSearchTableBody"></tbody>
      </table>
    </section>
  `;

  document.getElementById("snsSearchForm").addEventListener("submit", _handleCreate);
  _load();
}

export function destroy() {}

async function _load() {
  const status = document.getElementById("snsSearchStatus");
  const table = document.getElementById("snsSearchTable");
  status.textContent = "Loading...";
  table.hidden = true;

  try {
    const data = await api("/api/sns-search");
    _items = data.items || [];
    _renderDivisionOptions();
    _renderTable();
    status.textContent = _items.length ? "" : "No rows";
    table.hidden = !_items.length;
  } catch (err) {
    status.textContent = `Load failed: ${err.message}`;
  }
}

function _renderDivisionOptions() {
  const divisions = [...new Set(["Finance", ..._items.map((item) => item.Division).filter(Boolean)])].sort();
  document.getElementById("snsDivisionList").innerHTML = divisions
    .map((division) => `<option value="${escapeHtml(division)}"></option>`)
    .join("");
}

function _renderTable() {
  const body = document.getElementById("snsSearchTableBody");
  body.innerHTML = _items.map((item) => `
    <tr data-id="${item.ID_Sns_Search}">
      <td class="sns-search-id-col">${item.ID_Sns_Search}</td>
      <td>
        <input class="sns-search-cell-input" data-field="Division" value="${escapeHtml(item.Division)}">
      </td>
      <td>
        <textarea class="sns-search-cell-textarea" data-field="Words" rows="2">${escapeHtml(item.Words)}</textarea>
      </td>
      <td class="sns-search-actions">
        <button type="button" class="btn-secondary sns-search-save" data-action="save">Save</button>
        <button type="button" class="btn-danger sns-search-delete" data-action="delete">Delete</button>
      </td>
    </tr>
  `).join("");

  body.querySelectorAll("button[data-action='save']").forEach((button) => {
    button.addEventListener("click", () => _handleUpdate(button.closest("tr")));
  });
  body.querySelectorAll("button[data-action='delete']").forEach((button) => {
    button.addEventListener("click", () => _handleDelete(button.closest("tr")));
  });
}

async function _handleCreate(event) {
  event.preventDefault();
  const divisionEl = document.getElementById("snsDivisionInput");
  const wordsEl = document.getElementById("snsWordsInput");
  const payload = {
    Division: divisionEl.value.trim(),
    Words: wordsEl.value.trim(),
  };
  if (!payload.Division || !payload.Words) {
    _setStatus("Division and Words are required.", true);
    return;
  }

  try {
    await api("/api/sns-search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    wordsEl.value = "";
    _setStatus("Added.");
    await _load();
  } catch (err) {
    _setStatus(`Add failed: ${err.message}`, true);
  }
}

async function _handleUpdate(row) {
  if (!row) return;
  const id = row.dataset.id;
  const payload = _rowPayload(row);
  if (!payload.Division || !payload.Words) {
    _setStatus("Division and Words are required.", true);
    return;
  }

  try {
    await api(`/api/sns-search/${encodeURIComponent(id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    _setStatus("Saved.");
    await _load();
  } catch (err) {
    _setStatus(`Save failed: ${err.message}`, true);
  }
}

async function _handleDelete(row) {
  if (!row) return;
  const id = row.dataset.id;
  try {
    await api(`/api/sns-search/${encodeURIComponent(id)}`, { method: "DELETE" });
    _setStatus("Deleted.");
    await _load();
  } catch (err) {
    _setStatus(`Delete failed: ${err.message}`, true);
  }
}

function _rowPayload(row) {
  return {
    Division: row.querySelector("[data-field='Division']").value.trim(),
    Words: row.querySelector("[data-field='Words']").value.trim(),
  };
}

function _setStatus(message, isError = false) {
  const status = document.getElementById("snsSearchStatus");
  if (!status) return;
  status.textContent = message;
  status.classList.toggle("is-error", isError);
}
