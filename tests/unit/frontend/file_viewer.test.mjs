import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const fileViewerPath = resolve(__dirname, "../../../server/static/shared/file-viewer.js");

const translations = {
  "chat.file_viewer.notes": "Notes",
  "chat.file_viewer.slide": "Slide {n}",
  "chat.file_viewer.truncated": "Showing only part of the file",
};
const fileViewerSource = readFileSync(fileViewerPath, "utf8").replace(/^import .*;\r?\n/gm, "");
const stubs = `
  const t = (key, params = {}) => {
    let value = translations[key] || key;
    for (const [name, replacement] of Object.entries(params)) value = value.replaceAll("{" + name + "}", replacement);
    return value;
  };
  const basePath = "/app";
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  const renderSafeMarkdown = (text) => text;
  const formatChatFileSize = (bytes) => String(bytes) + " B";
  const getChatFileIcon = () => "📎";
  const translations = ${JSON.stringify(translations)};
`;
const fileViewerUrl = "data:text/javascript;base64," + Buffer.from(stubs + fileViewerSource).toString("base64");
const {
  docxBlocksToHtml,
  parseCsv,
  pptxSlidesToHtml,
  rowsToTableHtml,
  truncateViewerText,
} = await import(fileViewerUrl);

describe("file viewer helpers", () => {
  it("truncates large text previews", () => {
    assert.deepEqual(truncateViewerText("abcdef", 3), { text: "abc", truncated: true });
    assert.deepEqual(truncateViewerText("abc", 3), { text: "abc", truncated: false });
    assert.deepEqual(truncateViewerText(null, 3), { text: "", truncated: false });
  });

  it("parses quoted CSV fields, commas, newlines, and doubled quotes", () => {
    const text = 'a,b\r\n"c,d","e\nf"\r\n"g""h",i\r\n';
    assert.deepEqual(parseCsv(text), [
      ["a", "b"],
      ["c,d", "e\nf"],
      ['g"h', "i"],
    ]);
    assert.deepEqual(parseCsv(""), []);
  });

  it("renders CSV rows as a table with an escaped sticky header", () => {
    const html = rowsToTableHtml([["<name>", "value"], ["a&b", "1"]]);
    assert.match(html, /<table class="chat-file-viewer-table">/);
    assert.match(html, /<thead><tr><th>&lt;name&gt;<\/th><th>value<\/th><\/tr><\/thead>/);
    assert.match(html, /<tbody><tr><td>a&amp;b<\/td><td>1<\/td><\/tr><\/tbody>/);
    assert.match(rowsToTableHtml([]), /<table class="chat-file-viewer-table"><\/table>/);
  });

  it("renders docx headings, runs, nested lists, and tables with escaped text", () => {
    const html = docxBlocksToHtml([
      { type: "paragraph", style: "title", runs: [{ text: "Title" }] },
      {
        type: "paragraph",
        style: "heading2",
        runs: [
          { text: "A", bold: true, italic: false, underline: false },
          { text: "<B>", bold: false, italic: true, underline: true },
        ],
      },
      {
        type: "paragraph",
        style: null,
        list: { level: 0, ordered: false },
        runs: [{ text: "one" }],
      },
      {
        type: "paragraph",
        style: null,
        list: { level: 1, ordered: true },
        runs: [{ text: "nested" }],
      },
      {
        type: "paragraph",
        style: null,
        list: { level: 0, ordered: false },
        runs: [{ text: "two" }],
      },
      { type: "table", rows: [["a", "<x>"]] },
    ]);

    assert.match(html, /<h1>Title<\/h1>/);
    assert.match(html, /<strong>A<\/strong><em><u>&lt;B&gt;<\/u><\/em>/);
    assert.match(html, /<ul><li>one<ol><li>nested<\/li><\/ol><\/li><li>two<\/li><\/ul>/);
    assert.match(html, /<table class="chat-file-viewer-table docx-table"><tbody><tr><td>a<\/td><td>&lt;x&gt;<\/td><\/tr><\/tbody><\/table>/);
    assert.doesNotMatch(html, /<x>/);
  });

  it("renders pptx slides with escaped titles, body text, and collapsible notes", () => {
    const html = pptxSlidesToHtml([
      { index: 1, title: "<Title>", texts: ["line one", "<line two>"], notes: "<note>" },
    ]);
    assert.match(html, /class="chat-file-viewer-slide"/);
    assert.match(html, /Slide 1/);
    assert.match(html, /&lt;Title&gt;/);
    assert.match(html, /<li>line one<\/li><li>&lt;line two&gt;<\/li>/);
    assert.match(html, /<details class="chat-file-viewer-slide-notes"><summary>Notes<\/summary><div>&lt;note&gt;<\/div><\/details>/);
    assert.doesNotMatch(html, /<note>/);
  });
});
