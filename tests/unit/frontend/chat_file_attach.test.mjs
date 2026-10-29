import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const imageInputPath = resolve(__dirname, "../../../server/static/shared/image-input.js");
const renderUtilsPath = resolve(__dirname, "../../../server/static/shared/chat/render-utils.js");
const translations = {
  "chat.attach.size_bytes": "{size} B",
  "chat.attach.size_kb": "{size} KB",
  "chat.attach.size_mb": "{size} MB",
  "chat.line.reply": "Reply",
  "chat.line.copy": "Copy",
  "chat.line.download": "Download",
  "chat.line.waiting_reply": "Awaiting reply",
  "chat.line.reply_label": "Reply to",
  "chat.line.from_external": "From {via}",
  "chat.line.read": "Read",
  "chat.file_viewer.preview": "Preview",
  "chat.file_viewer.download": "Download",
};

const imageInputSource = readFileSync(imageInputPath, "utf8").replace(/^import .*;\r?\n/gm, "");
const imageInputStubs = `
  const t = (key, params = {}) => {
    let value = translations[key] || key;
    for (const [name, replacement] of Object.entries(params)) value = value.replaceAll("{" + name + "}", replacement);
    return value;
  };
  const basePath = "/app";
  const translations = ${JSON.stringify(translations)};
`;
const imageInputUrl = "data:text/javascript;base64," + Buffer.from(imageInputStubs + imageInputSource).toString("base64");
const { chatFileBadge, formatChatFileSize, getChatFileIcon, getChatFileKind, renderChatFiles, validateChatFileBatch } = await import(imageInputUrl);

const renderUtilsSource = readFileSync(renderUtilsPath, "utf8").replace(/^import .*;\r?\n/gm, "");
const renderUtilsStubs = `
  const t = (key, params = {}) => {
    let value = translations[key] || key;
    for (const [name, replacement] of Object.entries(params)) value = value.replaceAll("{" + name + "}", replacement);
    return value;
  };
  const _escapeAttr = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  const api = async () => ({ ok: true });
  const faceUrl = (name, emotion) => "/face/" + encodeURIComponent(name) + "/" + (emotion || "neutral");
  const bustUrl = (name, emotion) => "/bust/" + encodeURIComponent(name) + "/" + (emotion || "neutral");
  const translations = ${JSON.stringify(translations)};
`;
const renderUtilsUrl = "data:text/javascript;base64," + Buffer.from(renderUtilsStubs + renderUtilsSource).toString("base64");
const { renderHistoryMessage, renderLiveBubble } = await import(renderUtilsUrl);

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[ch]);

describe("chat file attachments", () => {
  it("chooses an icon for each common file category", () => {
    assert.equal(getChatFileIcon({ name: "report.pdf" }), "📕");
    assert.equal(getChatFileIcon({ name: "budget.xlsx" }), "📊");
    assert.equal(getChatFileIcon({ name: "notes.docx" }), "📄");
    assert.equal(getChatFileIcon({ media_type: "image/svg+xml" }), "🖼️");
    assert.equal(getChatFileIcon({ name: "voice.mp3" }), "🎵");
    assert.equal(getChatFileIcon({ name: "clip.mp4" }), "🎬");
    assert.equal(getChatFileIcon({ name: "archive.zip" }), "🗜️");
    assert.equal(getChatFileIcon({ name: "data.bin" }), "📎");
  });

  it("formats byte, kilobyte, and megabyte sizes", () => {
    assert.equal(formatChatFileSize(512), "512 B");
    assert.equal(formatChatFileSize(1536), "1.5 KB");
    assert.equal(formatChatFileSize(1572864), "1.5 MB");
  });

  it("enforces file count, per-file, empty-file, and total-size limits", () => {
    assert.equal(validateChatFileBatch([{ size: 1 }]), null);
    assert.equal(validateChatFileBatch(Array.from({ length: 11 }, () => ({ size: 1 }))), "chat.attach.limit_count");
    assert.equal(validateChatFileBatch([{ size: 25 * 1024 * 1024 + 1 }]), "chat.attach.limit_file_size");
    assert.equal(validateChatFileBatch([{ size: 0 }]), "chat.attach.empty_file");
    assert.equal(
      validateChatFileBatch([{ size: 25 * 1024 * 1024 }, { size: 25 * 1024 * 1024 + 1 }]),
      "chat.attach.limit_file_size",
    );
    assert.equal(
      validateChatFileBatch([{ size: 25 * 1024 * 1024 }, { size: 25 * 1024 * 1024 }]),
      null,
    );
    assert.equal(
      validateChatFileBatch([{ size: 30 * 1024 * 1024 }]),
      "chat.attach.limit_file_size",
    );
    assert.equal(
      validateChatFileBatch([{ size: 20 * 1024 * 1024 }, { size: 20 * 1024 * 1024 }, { size: 10 * 1024 * 1024 + 1 }]),
      "chat.attach.limit_total_size",
    );
  });

  it("classifies files from MIME type first, then extension", () => {
    assert.equal(getChatFileKind({ name: "photo.bin", media_type: "image/png" }), "image");
    assert.equal(getChatFileKind({ name: "clip.mp4" }), "video");
    assert.equal(getChatFileKind({ name: "voice.mp3", media_type: "application/octet-stream" }), "audio");
    assert.equal(getChatFileKind({ name: "report.pdf" }), "pdf");
    assert.equal(getChatFileKind({ name: "README.md" }), "markdown");
    assert.equal(getChatFileKind({ name: "data.csv" }), "csv");
    assert.equal(getChatFileKind({ name: "notes.txt" }), "text");
    assert.equal(getChatFileKind({ name: "script.py", media_type: "text/x-python" }), "text");
    assert.equal(getChatFileKind({ name: "book.xlsx" }), "xlsx");
    assert.equal(getChatFileKind({ name: "letter.docx" }), "docx");
    assert.equal(getChatFileKind({ name: "deck.pptx" }), "pptx");
    assert.equal(getChatFileKind({ name: "vector.svg" }), "other");
    assert.equal(getChatFileKind({ name: "vector.svg", media_type: "image/svg+xml" }), "other");
    assert.equal(getChatFileKind({ name: "page.html", media_type: "text/html" }), "other");
    assert.equal(getChatFileKind({ name: "archive.zip" }), "other");
    assert.equal(getChatFileKind({ name: "plain.md", media_type: "text/plain" }), "text");
  });

  it("renders media, preview cards, and legacy chips by file kind", () => {
    const base = { path: "attachments/example", size: 1536 };
    const imageHtml = renderChatFiles([{ ...base, name: "photo.png", media_type: "image/png" }], { animaName: "mei" });
    assert.match(imageHtml, /class="chat-attached-image"/);
    assert.match(imageHtml, /src="\/app\/api\/animas\/mei\/attachments\/example\?inline=1"/);
    assert.match(imageHtml, /loading="lazy"/);

    const audioHtml = renderChatFiles([{ ...base, name: "voice.mp3", media_type: "audio/mpeg" }], { animaName: "mei" });
    assert.match(audioHtml, /<audio controls preload="metadata" src="\/app\/api\/animas\/mei\/attachments\/example\?inline=1"><\/audio>/);
    assert.match(audioHtml, /class="chat-file-card-download"/);

    const videoHtml = renderChatFiles([{ ...base, name: "clip.mp4" }], { animaName: "mei" });
    assert.match(videoHtml, /<video controls playsinline preload="metadata" src="\/app\/api\/animas\/mei\/attachments\/example\?inline=1"><\/video>/);

    const pdfHtml = renderChatFiles([{ ...base, name: "report.pdf", media_type: "application/pdf" }], { animaName: "mei" });
    assert.match(pdfHtml, /<div class="chat-file-card chat-file-kind-pdf"><button type="button" class="chat-file-card-open" data-chat-file-preview/);
    assert.match(pdfHtml, /data-kind="pdf"/);
    assert.match(pdfHtml, /data-anima="mei"/);
    assert.match(pdfHtml, /data-stored-name="example"/);
    assert.match(pdfHtml, /href="\/app\/api\/animas\/mei\/attachments\/example" download="report\.pdf"/);

    const zipHtml = renderChatFiles([{ ...base, name: "archive.zip" }], { animaName: "mei" });
    assert.match(zipHtml, /class="chat-file-chip" href="\/app\/api\/animas\/mei\/attachments\/example"/);
    assert.doesNotMatch(zipHtml, /data-chat-file-preview/);

    const localHtml = renderChatFiles([{ name: "local.pdf", size: 10 }], { animaName: "mei" });
    assert.match(localHtml, /class="chat-file-chip"/);
    assert.doesNotMatch(localHtml, /data-chat-file-preview/);
  });

  it("renders preview cards with safe download links in both user and Anima bubbles", () => {
    const file = {
      name: "見積書.pdf",
      media_type: "application/pdf",
      size: 1258291,
      path: "attachments/20261029_101500_0_見積書.pdf",
    };
    const opts = {
      lineChat: true,
      animaName: "mei",
      currentUserNames: new Set(["alice"]),
      knownAnimaNames: new Set(["mei"]),
      escapeHtml,
      renderMarkdown: (text) => `<p>${escapeHtml(text)}</p>`,
      renderChatFiles,
      smartTimestamp: () => "10:15",
    };
    const userHtml = renderHistoryMessage({ role: "human", content: "見てください", from_person: "alice", files: [file] }, opts);
    const animaHtml = renderHistoryMessage({ role: "assistant", content: "確認します", files: [file] }, opts);
    const optimisticHtml = renderLiveBubble({ role: "user", text: "見てください", files: [{ ...file, path: undefined }] }, opts);

    assert.match(userHtml, /class="chat-line chat-line--me"/);
    assert.match(animaHtml, /class="chat-line chat-line--anima"/);
    for (const html of [userHtml, animaHtml]) {
      assert.match(html, /class="chat-file-card-open" data-chat-file-preview/);
      assert.match(html, /href="\/app\/api\/animas\/mei\/attachments\//);
      assert.match(html, /download="見積書\.pdf"/);
      assert.match(html, /1\.2 MB/);
    }
    assert.match(optimisticHtml, /class="chat-file-chip-name">見積書\.pdf/);
    assert.doesNotMatch(optimisticHtml, /<a class="chat-file-chip"/);

    const escaped = renderChatFiles([{ name: "<script>.txt", size: 1, path: "attachments/x.txt" }], { animaName: "mei" });
    assert.match(escaped, /&lt;script&gt;\.txt/);
    assert.match(escaped, /data-name="&lt;script&gt;\.txt"/);
    assert.doesNotMatch(escaped, /<script>/);
  });
  it("labels file cards with a short type badge", () => {
    assert.equal(chatFileBadge({ name: "見積書.pdf" }), "PDF");
    assert.equal(chatFileBadge({ name: "売上.xlsx" }), "XLSX");
    assert.equal(chatFileBadge({ name: "notes" , media_type: "text/markdown" }), "MD");
    assert.equal(chatFileBadge({ name: "archive.backup" }), "FILE");
    assert.equal(chatFileBadge({ name: "<x>.<b>" }), "FILE");
  });
});
