import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  clientToCanvasPoint,
  hitTestAnima,
} from "../../../server/static/workspace/pixel/modules/hit-test.js";

const actors = [{ name: "luna", x: 40, y: 20, width: 24, height: 32 }];

describe("clientToCanvasPoint", () => {
  it("maps enlarged CSS display coordinates into logical canvas coordinates", () => {
    assert.deepEqual(
      clientToCanvasPoint(210, 120, { left: 10, top: 20, width: 400, height: 200 }, 200, 100),
      { x: 100, y: 50 },
    );
  });

  it("maps a CSS-shrunk canvas back into logical canvas coordinates", () => {
    assert.deepEqual(
      clientToCanvasPoint(35, 30, { left: 10, top: 20, width: 100, height: 50 }, 200, 100),
      { x: 50, y: 20 },
    );
  });

  it("rejects pointers outside the canvas or invalid display dimensions", () => {
    assert.equal(
      clientToCanvasPoint(9, 20, { left: 10, top: 20, width: 100, height: 50 }, 200, 100),
      null,
    );
    assert.equal(
      clientToCanvasPoint(10, 20, { left: 10, top: 20, width: 0, height: 50 }, 200, 100),
      null,
    );
  });
});

describe("hitTestAnima", () => {
  it("hits the same logical character when the canvas is enlarged", () => {
    assert.equal(hitTestAnima({
      clientX: 100,
      clientY: 40,
      rect: { left: 0, top: 0, width: 400, height: 200 },
      logicalWidth: 200,
      logicalHeight: 100,
      actors,
    }), "luna");
  });

  it("hits the same logical character when the canvas is shrunk", () => {
    assert.equal(hitTestAnima({
      clientX: 30,
      clientY: 10,
      rect: { left: 0, top: 0, width: 100, height: 50 },
      logicalWidth: 200,
      logicalHeight: 100,
      actors,
    }), "luna");
  });

  it("prefers the actor drawn later when hit areas overlap", () => {
    assert.equal(hitTestAnima({
      clientX: 15,
      clientY: 15,
      rect: { left: 0, top: 0, width: 100, height: 100 },
      logicalWidth: 100,
      logicalHeight: 100,
      actors: [
        { name: "behind", x: 0, y: 0, width: 30, height: 30 },
        { name: "front", x: 10, y: 10, width: 30, height: 30 },
      ],
    }), "front");
  });

  it("returns null when an empty area is clicked", () => {
    assert.equal(hitTestAnima({
      clientX: 90,
      clientY: 90,
      rect: { left: 0, top: 0, width: 100, height: 100 },
      logicalWidth: 100,
      logicalHeight: 100,
      actors,
    }), null);
  });
});
