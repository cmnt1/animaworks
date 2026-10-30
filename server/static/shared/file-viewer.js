// ── Chat File Viewer ────────────────────────────────────
// Full-screen preview for text-like files, Office previews, and PDFs.

import { t } from "/shared/i18n.js";
import { basePath } from "/shared/base-path.js";
import { escapeHtml } from "/shared/html-utils.js";
import { renderSafeMarkdown } from "../modules/state.js";
import { CHAT_FILE_DOWNLOAD_ICON, chatFileBadge, formatChatFileSize } from "/shared/image-input.js";

const MAX_TEXT_CHARS = 2 * 1024 * 1024;
const MAX_CSV_ROWS = 1000;
const PDF_MODULE_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/legacy/build/pdf.min.mjs";
const PDF_WORKER_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/legacy/build/pdf.worker.min.mjs";

let _initialized = false;
let _activeViewer = null;

/**
 * Cut very large text previews at the 2MB mark.
 * @returns {{text: string, truncated: boolean}}
 */
export function truncateViewerText(text, maxChars = MAX_TEXT_CHARS) {
  const value = String(text ?? "");
  if (value.length <= maxChars) return { text: value, truncated: false };
  return { text: value.slice(0, maxChars), truncated: true };
}

/**
 * Parse CSV text, including quoted commas, quoted newlines, and doubled quotes.
 * @returns {string[][]}
 */
export function parseCsv(text) {
  const source = String(text ?? "").replace(/^\uFEFF/, "");
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < source.length; i += 1) {
    const ch = source[i];
    if (inQuotes) {
      if (ch === '"') {
        if (source[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        field += ch;
      }
      continue;
    }

    if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (ch === "\r") {
      if (source[i + 1] === "\n") i += 1;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += ch;
    }
  }

  if (field !== "" || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

/** Render rows as an HTML table whose first row is the sticky heading row. */
export function rowsToTableHtml(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return '<table class="chat-file-viewer-table"></table>';
  }
  const cell = (value) => escapeHtml(value == null ? "" : String(value));
  // Rows can be ragged (trailing cells are trimmed); pad so every row has the same grid.
  const width = Math.max(...rows.map((row) => (Array.isArray(row) ? row.length : 0)));
  const pad = (row) => Array.from({ length: width }, (_, i) => (Array.isArray(row) ? row[i] : ""));
  const head = pad(rows[0]).map((value) => `<th>${cell(value)}</th>`).join("");
  const body = rows.slice(1)
    .map((row) => `<tr>${pad(row).map((value) => `<td>${cell(value)}</td>`).join("")}</tr>`)
    .join("");
  return `<table class="chat-file-viewer-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function _runsHtml(runs = []) {
  return (Array.isArray(runs) ? runs : []).map((run) => {
    let html = escapeHtml(run?.text ?? "").replace(/\n/g, "<br>");
    if (run?.underline) html = `<u>${html}</u>`;
    if (run?.italic) html = `<em>${html}</em>`;
    if (run?.bold) html = `<strong>${html}</strong>`;
    return html;
  }).join("");
}

function _docxTableHtml(rows = []) {
  const tableRows = (Array.isArray(rows) ? rows : []).map((row) => {
    const cells = (Array.isArray(row) ? row : []).map((value) => `<td>${escapeHtml(value ?? "")}</td>`).join("");
    return `<tr>${cells}</tr>`;
  }).join("");
  return `<table class="chat-file-viewer-table docx-table"><tbody>${tableRows}</tbody></table>`;
}

function _buildListTree(items) {
  const roots = [];
  const stack = [];
  for (const item of items) {
    const level = Math.max(0, Number(item.level) || 0);
    while (stack.length > 0 && level <= stack[stack.length - 1].level) stack.pop();
    const node = { item, children: [] };
    if (stack.length > 0) stack[stack.length - 1].node.children.push(node);
    else roots.push(node);
    stack.push({ level, node });
  }
  return roots;
}

function _renderListNodes(nodes) {
  let html = "";
  let index = 0;
  while (index < nodes.length) {
    const ordered = Boolean(nodes[index].item.ordered);
    const tag = ordered ? "ol" : "ul";
    html += `<${tag}>`;
    while (index < nodes.length && Boolean(nodes[index].item.ordered) === ordered) {
      const node = nodes[index];
      html += `<li>${_runsHtml(node.item.runs)}${_renderListNodes(node.children)}</li>`;
      index += 1;
    }
    html += `</${tag}>`;
  }
  return html;
}

/** Convert the docx preview API blocks into safe HTML. */
export function docxBlocksToHtml(blocks = []) {
  const list = Array.isArray(blocks) ? blocks : [];
  const output = [];
  let index = 0;

  while (index < list.length) {
    const block = list[index] || {};
    if (block.type === "table") {
      output.push(_docxTableHtml(block.rows));
      index += 1;
      continue;
    }
    if (block.type !== "paragraph") {
      index += 1;
      continue;
    }
    if (block.list) {
      const items = [];
      while (index < list.length && list[index]?.type === "paragraph" && list[index]?.list) {
        items.push({
          level: list[index].list.level,
          ordered: list[index].list.ordered,
          runs: list[index].runs,
        });
        index += 1;
      }
      output.push(_renderListNodes(_buildListTree(items)));
      continue;
    }
    const runs = _runsHtml(block.runs);
    const heading = /^heading([1-6])$/.exec(String(block.style || ""));
    if (block.style === "title") output.push(`<h1>${runs}</h1>`);
    else if (heading) output.push(`<h${heading[1]}>${runs}</h${heading[1]}>`);
    else output.push(`<p>${runs}</p>`);
    index += 1;
  }

  return output.join("");
}

/** Render the pptx preview API slides as cards. */
export function pptxSlidesToHtml(slides = []) {
  const list = Array.isArray(slides) ? slides : [];
  return list.map((slide, index) => {
    const number = Number.isInteger(slide?.index) ? slide.index : index + 1;
    const title = slide?.title ? `<h3>${escapeHtml(slide.title)}</h3>` : "";
    const texts = Array.isArray(slide?.texts) ? slide.texts : [];
    const body = texts.length
      ? `<ul class="chat-file-viewer-slide-text">${texts.map((text) => `<li>${escapeHtml(text)}</li>`).join("")}</ul>`
      : "";
    const notes = slide?.notes
      ? `<details class="chat-file-viewer-slide-notes"><summary>${escapeHtml(t("chat.file_viewer.notes"))}</summary>`
        + `<div>${escapeHtml(slide.notes)}</div></details>`
      : "";
    return `<section class="chat-file-viewer-slide">`
      + `<div class="chat-file-viewer-slide-head"><span class="chat-file-viewer-slide-number">`
      + `${escapeHtml(t("chat.file_viewer.slide", { n: String(number) }))}</span>${title}</div>`
      + `${body}${notes}</section>`;
  }).join("");
}

/** Initialize the document-level click delegation for preview cards. */
export function initFileViewer() {
  if (_initialized) return;
  _initialized = true;

  document.addEventListener("click", (event) => {
    const card = event.target.closest?.("[data-chat-file-preview]");
    if (!card) return;
    if (event.target.closest?.(".chat-file-card-download")) return;
    event.preventDefault();
    openFileViewer({
      anima: card.dataset.anima || "",
      storedName: card.dataset.storedName || "",
      name: card.dataset.name || "file",
      size: Number(card.dataset.size) || 0,
      kind: card.dataset.kind || "other",
    });
  });
}

function _attachmentUrl(anima, storedName) {
  return `${basePath}/api/animas/${encodeURIComponent(anima)}/attachments/${encodeURIComponent(storedName)}`;
}

function _previewUrl(anima, storedName) {
  return `${_attachmentUrl(anima, storedName)}/preview`;
}

async function _responseDetail(response) {
  let raw = "";
  try {
    raw = await response.text();
  } catch {
    return response.statusText || "";
  }
  try {
    const data = JSON.parse(raw);
    if (data && data.detail) return String(data.detail);
  } catch {
    // Not JSON: fall back to a short text response.
  }
  return raw.slice(0, 500) || response.statusText || "";
}

async function _fetchText(url) {
  const response = await fetch(url, { credentials: "same-origin" });
  if (!response.ok) throw new Error(await _responseDetail(response));
  return response.text();
}

async function _fetchJson(url) {
  const response = await fetch(url, { credentials: "same-origin" });
  if (!response.ok) throw new Error(await _responseDetail(response));
  return response.json();
}

function _truncatedNote() {
  return `<p class="chat-file-viewer-note">${escapeHtml(t("chat.file_viewer.truncated"))}</p>`;
}

function _errorHtml(message, url, name) {
  const detail = message || t("chat.file_viewer.error");
  return `<div class="chat-file-viewer-error" role="alert">`
    + `<p>${escapeHtml(detail)}</p>`
    + `<a class="chat-file-viewer-error-download" href="${escapeHtml(url)}" download="${escapeHtml(name)}">`
    + `${escapeHtml(t("chat.file_viewer.download"))}</a></div>`;
}

function _setLinks(container) {
  container.querySelectorAll("a").forEach((anchor) => {
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
  });
}

let _fileMarked = null;

/**
 * Render a Markdown file with raw HTML shown as text.
 * renderSafeMarkdown escapes before parsing, which double-escapes code blocks, so
 * a private marked instance escapes only the HTML tokens instead.
 */
export function renderFileMarkdown(text) {
  const md = globalThis.marked;
  if (!md?.Marked) return renderSafeMarkdown(text);
  if (!_fileMarked) {
    _fileMarked = new md.Marked({ gfm: true });
    _fileMarked.use({
      renderer: {
        html(token) {
          return escapeHtml(typeof token === "string" ? token : token?.text ?? "");
        },
      },
    });
  }
  return _fileMarked.parse(String(text ?? ""));
}

/** Drop link and image targets that are not plain web URLs. */
function _sanitizeUrls(container) {
  container.querySelectorAll("a[href]").forEach((anchor) => {
    if (!/^(https?:|mailto:|#)/i.test(anchor.getAttribute("href") || "")) anchor.removeAttribute("href");
  });
  container.querySelectorAll("img").forEach((img) => {
    if (!/^https?:/i.test(img.getAttribute("src") || "")) img.remove();
  });
}

async function _renderMarkdown(body, url) {
  const raw = await _fetchText(`${url}?inline=1`);
  const limited = truncateViewerText(raw);
  body.innerHTML = `<div class="chat-file-viewer-md">${renderFileMarkdown(limited.text)}</div>`
    + (limited.truncated ? _truncatedNote() : "");
  _sanitizeUrls(body);
  _setLinks(body);
}

function _formatJson(text, name) {
  const trimmed = text.trim();
  const looksLikeJson = /\.json$/i.test(String(name || ""))
    || trimmed.startsWith("{") || trimmed.startsWith("[");
  if (!looksLikeJson) return text;
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

async function _renderText(body, url, name) {
  const raw = await _fetchText(`${url}?inline=1`);
  const limited = truncateViewerText(raw);
  const text = _formatJson(limited.text, name);
  body.innerHTML = `<pre class="chat-file-viewer-pre"><code>${escapeHtml(text)}</code></pre>`
    + (limited.truncated ? _truncatedNote() : "");
}

async function _renderCsv(body, url) {
  const raw = await _fetchText(`${url}?inline=1`);
  const limited = truncateViewerText(raw);
  const rows = parseCsv(limited.text);
  const shown = rows.slice(0, MAX_CSV_ROWS);
  body.innerHTML = `<div class="chat-file-viewer-table-wrap">${rowsToTableHtml(shown)}</div>`
    + (limited.truncated || rows.length > MAX_CSV_ROWS ? _truncatedNote() : "");
}

function _renderSheet(body, sheet, showHeading, forceTruncated = false) {
  const rows = Array.isArray(sheet?.rows) ? sheet.rows : [];
  const heading = showHeading && sheet?.name
    ? `<h3 class="chat-file-viewer-sheet-name">${escapeHtml(sheet.name)}</h3>`
    : "";
  body.innerHTML = heading
    + `<div class="chat-file-viewer-table-wrap">${rowsToTableHtml(rows)}</div>`
    + (sheet?.truncated || forceTruncated ? _truncatedNote() : "");
}

async function _renderXlsx(body, url) {
  const data = await _fetchJson(url);
  const sheets = Array.isArray(data?.sheets) ? data.sheets : [];
  if (sheets.length === 0) {
    body.innerHTML = `<div class="chat-file-viewer-table-wrap">${rowsToTableHtml([])}</div>`;
    return;
  }

  const showTabs = sheets.length > 1;
  const tabs = showTabs
    ? `<div class="chat-file-viewer-tabs" role="tablist">${sheets.map((sheet, index) =>
      `<button type="button" role="tab" class="chat-file-viewer-tab" data-sheet-index="${index}"`
      + ` aria-selected="${index === 0 ? "true" : "false"}">`
      + `${escapeHtml(sheet?.name || t("chat.file_viewer.sheet"))}</button>`).join("")}</div>`
    : "";
  body.innerHTML = `${tabs}<div class="chat-file-viewer-panel"></div>`;
  const panel = body.querySelector(".chat-file-viewer-panel");
  const show = (index) => {
    _renderSheet(panel, sheets[index], showTabs, Boolean(data?.truncated));
    body.querySelectorAll(".chat-file-viewer-tab").forEach((tab) => {
      const selected = Number(tab.dataset.sheetIndex) === index;
      tab.classList.toggle("active", selected);
      tab.setAttribute("aria-selected", selected ? "true" : "false");
    });
  };
  body.querySelectorAll(".chat-file-viewer-tab").forEach((tab) => {
    tab.addEventListener("click", () => show(Number(tab.dataset.sheetIndex) || 0));
  });
  show(0);
}

async function _renderDocx(body, url) {
  const data = await _fetchJson(url);
  body.innerHTML = `<div class="chat-file-viewer-doc">${docxBlocksToHtml(data?.blocks)}</div>`
    + (data?.truncated ? _truncatedNote() : "");
}

async function _renderPptx(body, url) {
  const data = await _fetchJson(url);
  body.innerHTML = `<div class="chat-file-viewer-slides">${pptxSlidesToHtml(data?.slides)}</div>`
    + (data?.truncated ? _truncatedNote() : "");
}

function _renderPdfFallback(body, url, name) {
  const src = `${url}?inline=1`;
  body.innerHTML = `<div class="chat-file-viewer-pdf-fallback">`
    + `<iframe src="${escapeHtml(src)}" title="${escapeHtml(name)}"></iframe>`
    + `<a href="${escapeHtml(src)}" target="_blank" rel="noopener noreferrer">`
    + `${escapeHtml(t("chat.file_viewer.open_new_tab"))}</a></div>`;
}

async function _renderPdf(body, viewer, url, name) {
  try {
    const module = await import(PDF_MODULE_URL);
    const pdfjs = module.default || module;
    pdfjs.GlobalWorkerOptions.workerSrc = PDF_WORKER_URL;
    const loadingTask = pdfjs.getDocument({ url: `${url}?inline=1`, withCredentials: true });
    const pdf = await loadingTask.promise;
    if (viewer.closed) {
      void pdf.destroy();
      return;
    }
    viewer.pdfDoc = pdf;

    const pages = [];
    const ratios = [];
    for (let index = 1; index <= pdf.numPages; index += 1) {
      const page = await pdf.getPage(index);
      const viewport = page.getViewport({ scale: 1 });
      pages.push(page);
      ratios.push(viewport.width / viewport.height);
    }
    if (viewer.closed) return;

    body.innerHTML = `<div class="chat-file-viewer-pdf"></div>`;
    const container = body.querySelector(".chat-file-viewer-pdf");
    const wrappers = [];
    const rendered = new Set();

    for (let index = 0; index < pages.length; index += 1) {
      const wrapper = document.createElement("div");
      wrapper.className = "chat-file-viewer-pdf-page";
      wrapper.style.aspectRatio = String(ratios[index] || 0.707);
      wrapper.innerHTML = `<span class="chat-file-viewer-pdf-page-number">`
        + `${escapeHtml(t("chat.file_viewer.page", { n: String(index + 1), total: String(pages.length) }))}</span>`;
      container.appendChild(wrapper);
      wrappers.push(wrapper);
    }

    const drawPage = async (index) => {
      if (viewer.closed || rendered.has(index)) return;
      rendered.add(index);
      const wrapper = wrappers[index];
      const page = pages[index];
      const cssWidth = Math.max(1, wrapper.clientWidth || Math.min(window.innerWidth - 32, 900));
      const base = page.getViewport({ scale: 1 });
      const scale = cssWidth / base.width;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const viewport = page.getViewport({ scale: scale * dpr });
      const canvas = document.createElement("canvas");
      canvas.className = "chat-file-viewer-pdf-canvas";
      canvas.width = Math.max(1, Math.floor(viewport.width));
      canvas.height = Math.max(1, Math.floor(viewport.height));
      canvas.style.width = "100%";
      canvas.style.height = "auto";
      const context = canvas.getContext("2d");
      try {
        await page.render({ canvasContext: context, viewport }).promise;
      } catch {
        rendered.delete(index);
        return;
      }
      if (viewer.closed) return;
      wrapper.insertBefore(canvas, wrapper.firstChild);
    };

    if (typeof IntersectionObserver === "undefined") {
      for (let index = 0; index < pages.length; index += 1) await drawPage(index);
      return;
    }

    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const index = wrappers.indexOf(entry.target);
        observer.unobserve(entry.target);
        if (index >= 0) void drawPage(index);
      }
    }, { root: body, rootMargin: "300px" });
    viewer.observer = observer;
    wrappers.forEach((wrapper) => observer.observe(wrapper));
  } catch {
    if (!viewer.closed) _renderPdfFallback(body, url, name);
  }
}

/**
 * Open the full-screen file viewer.
 * @param {object} options
 * @param {string} options.anima
 * @param {string} options.storedName
 * @param {string} options.name
 * @param {number} options.size
 * @param {string} options.kind
 */
export function openFileViewer({ anima, storedName, name, size, kind } = {}) {
  if (!anima || !storedName) return;
  _activeViewer?.close();

  const safeName = String(name || "file");
  const url = _attachmentUrl(anima, storedName);
  const previewUrl = _previewUrl(anima, storedName);
  const overlay = document.createElement("div");
  overlay.className = "chat-file-viewer-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", safeName);

  const viewer = {
    overlay,
    closed: false,
    pdfDoc: null,
    observer: null,
    objectUrls: [],
    close: null,
  };
  _activeViewer = viewer;

  overlay.innerHTML = `<div class="chat-file-viewer">`
    + `<div class="chat-file-viewer-header">`
    + `<div class="chat-file-viewer-title">`
    + `<span class="chat-file-card-badge chat-file-kind-${escapeHtml(kind || "other")}">`
    + `${escapeHtml(chatFileBadge({ name: safeName }, kind))}</span>`
    + `<span class="chat-file-viewer-filename">${escapeHtml(safeName)}</span>`
    + `<span class="chat-file-viewer-size">${escapeHtml(formatChatFileSize(size))}</span></div>`
    + `<div class="chat-file-viewer-actions">`
    + `<a class="chat-file-viewer-download" href="${escapeHtml(url)}" download="${escapeHtml(safeName)}" `
    + `title="${escapeHtml(t("chat.file_viewer.download"))}" aria-label="${escapeHtml(t("chat.file_viewer.download"))}">`
    + `${CHAT_FILE_DOWNLOAD_ICON}</a>`
    + `<button type="button" class="chat-file-viewer-close" `
    + `title="${escapeHtml(t("chat.file_viewer.close"))}" `
    + `aria-label="${escapeHtml(t("chat.file_viewer.close"))}">&times;</button></div></div>`
    + `<div class="chat-file-viewer-body"><div class="chat-file-viewer-loading">`
    + `${escapeHtml(t("chat.file_viewer.loading"))}</div></div></div>`;

  const onKeyDown = (event) => {
    if (event.key === "Escape") viewer.close();
  };
  const close = () => {
    if (viewer.closed) return;
    viewer.closed = true;
    viewer.observer?.disconnect();
    try {
      void viewer.pdfDoc?.destroy();
    } catch {
      // Ignore teardown errors from pdf.js.
    }
    viewer.objectUrls.forEach((objectUrl) => URL.revokeObjectURL(objectUrl));
    overlay.remove();
    document.removeEventListener("keydown", onKeyDown);
    if (_activeViewer === viewer) _activeViewer = null;
  };
  viewer.close = close;

  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) close();
  });
  document.addEventListener("keydown", onKeyDown);
  overlay.querySelector(".chat-file-viewer-close").addEventListener("click", close);
  document.body.appendChild(overlay);

  const body = overlay.querySelector(".chat-file-viewer-body");
  const showError = (error) => {
    if (viewer.closed) return;
    body.innerHTML = _errorHtml(error?.message || t("chat.file_viewer.error"), url, safeName);
  };

  const render = async () => {
    switch (kind) {
      case "markdown":
        await _renderMarkdown(body, url);
        break;
      case "text":
        await _renderText(body, url, safeName);
        break;
      case "csv":
        await _renderCsv(body, url);
        break;
      case "xlsx":
        await _renderXlsx(body, previewUrl);
        break;
      case "docx":
        await _renderDocx(body, previewUrl);
        break;
      case "pptx":
        await _renderPptx(body, previewUrl);
        break;
      case "pdf":
        await _renderPdf(body, viewer, url, safeName);
        break;
      default:
        _renderPdfFallback(body, url, safeName);
        break;
    }
  };

  void render().catch(showError);
}
