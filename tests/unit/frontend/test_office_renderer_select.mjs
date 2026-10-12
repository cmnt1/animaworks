import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  normalizeWorkspaceView,
  selectOfficeRenderer,
} from "../../../server/static/workspace/modules/office-renderer-selection.js";

describe("selectOfficeRenderer", () => {
  it("gives an explicit URL renderer precedence over localStorage", () => {
    assert.deepEqual(selectOfficeRenderer("?renderer=3d", "pixel"), {
      renderer: "3d",
      source: "url",
    });
  });

  it("uses the saved renderer when the URL does not specify a valid one", () => {
    assert.deepEqual(selectOfficeRenderer("?renderer=unknown", "3d"), {
      renderer: "3d",
      source: "localStorage",
    });
  });

  it("defaults to pixel when neither source has a valid preference", () => {
    assert.deepEqual(selectOfficeRenderer("", null), {
      renderer: "pixel",
      source: "default",
    });
    assert.deepEqual(selectOfficeRenderer("?renderer=unknown", "old-value"), {
      renderer: "pixel",
      source: "default",
    });
  });
});

describe("normalizeWorkspaceView", () => {
  it("migrates the old 3d view value to office", () => {
    assert.equal(normalizeWorkspaceView("3d"), "office");
  });

  it("preserves valid views and applies a fallback for missing values", () => {
    assert.equal(normalizeWorkspaceView("office"), "office");
    assert.equal(normalizeWorkspaceView("org"), "org");
    assert.equal(normalizeWorkspaceView(null, "org"), "org");
  });
});
