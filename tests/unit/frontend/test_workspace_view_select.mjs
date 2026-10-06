import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  normalizeWorkspaceView,
  selectWorkspaceView,
} from "../../../server/static/workspace/modules/office-renderer-selection.js";

describe("selectWorkspaceView", () => {
  it("gives a valid URL view precedence over localStorage", () => {
    assert.deepEqual(selectWorkspaceView("?view=battle", "org", "office"), {
      view: "battle",
      source: "url",
    });
  });

  it("uses a saved view when the URL does not contain a valid view", () => {
    assert.deepEqual(selectWorkspaceView("", "org", "office"), {
      view: "org",
      source: "localStorage",
    });
    assert.deepEqual(selectWorkspaceView("?view=unknown", "battle", "office"), {
      view: "battle",
      source: "localStorage",
    });
  });

  it("falls back to the default for unknown values", () => {
    assert.deepEqual(selectWorkspaceView("?view=unknown", "invalid", "org"), {
      view: "org",
      source: "default",
    });
    assert.deepEqual(selectWorkspaceView("", null, "invalid"), {
      view: "office",
      source: "default",
    });
    assert.equal(normalizeWorkspaceView("unknown", "battle"), "battle");
  });

  it("migrates the old 3d view value to office", () => {
    assert.deepEqual(selectWorkspaceView("", "3d", "org"), {
      view: "office",
      source: "localStorage",
    });
    assert.equal(normalizeWorkspaceView("3d"), "office");
  });
});
