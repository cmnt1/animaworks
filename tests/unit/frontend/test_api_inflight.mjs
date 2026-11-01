/** In-flight GET requests for the same API URL are shared. */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(resolve(__dirname, "../../../server/static/modules/api.js"), "utf8")
  .replace(/^import \{ createLogger \} from .*;$/m, 'const createLogger = () => ({ warn() {}, error() {} });')
  .replace(/^import \{ basePath \} from .*;$/m, 'const basePath = "";');
const moduleUrl = "data:text/javascript;base64," + Buffer.from(source, "utf8").toString("base64");
const { api } = await import(moduleUrl);

describe("api in-flight requests", () => {
  it("coalesces concurrent GETs to the same URL and clears the entry afterward", async () => {
    const oldFetch = globalThis.fetch;
    let calls = 0;
    let resolveFetch;
    globalThis.fetch = () => {
      calls += 1;
      if (calls > 1) {
        return Promise.resolve({ status: 200, ok: true, json: async () => ({ name: "alice" }) });
      }
      return new Promise((resolve) => { resolveFetch = resolve; });
    };
    try {
      const first = api("/api/animas/alice/summary");
      const second = api("/api/animas/alice/summary");
      assert.equal(first, second);
      assert.equal(calls, 1);

      resolveFetch({ status: 200, ok: true, json: async () => ({ name: "alice" }) });
      assert.deepEqual(await Promise.all([first, second]), [{ name: "alice" }, { name: "alice" }]);

      await api("/api/animas/alice/summary");
      assert.equal(calls, 2);
    } finally {
      globalThis.fetch = oldFetch;
    }
  });
});
