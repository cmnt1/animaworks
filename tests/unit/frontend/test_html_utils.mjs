import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { escapeAttr, escapeHtml, timeStr } from "../../../server/static/shared/html-utils.js";

describe("shared HTML utilities", () => {
  it("escapes HTML text and quoted attribute values, including apostrophes", () => {
    const source = `&<>"'`;
    const escaped = "&amp;&lt;&gt;&quot;&#39;";

    assert.equal(escapeHtml(source), escaped);
    assert.equal(escapeAttr(source), escaped);
  });

  it("handles nullish input and invalid timestamps safely", () => {
    assert.equal(escapeHtml(null), "");
    assert.equal(escapeAttr(undefined), "");
    assert.equal(timeStr("not a timestamp"), "--:--");
  });
});
