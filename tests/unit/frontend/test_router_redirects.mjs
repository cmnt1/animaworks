/**
 * Unit tests for router redirect table and anima subPath parsing.
 *
 * Run with: node --test tests/unit/frontend/test_router_redirects.mjs
 *
 * router.js imports i18n via an absolute path ("/shared/..."), which Node
 * cannot resolve, so we load the module source with that import stubbed out.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROUTER_PATH = resolve(
  __dirname,
  "../../../server/static/modules/router.js",
);

const source = readFileSync(ROUTER_PATH, "utf8")
  .replace(
    /^import\s+\{\s*applyTranslations,\s*t\s*\}\s+from\s+["'][^"']+["'];?\s*$/m,
    `export function applyTranslations() {}\nexport function t(k) { return k; }`,
  );

const moduleUrl =
  "data:text/javascript;base64," + Buffer.from(source, "utf8").toString("base64");

const {
  REDIRECTS,
  resolveRedirect,
  resolveRouteMatch,
  parseAnimaSubPath,
} = await import(moduleUrl);

describe("REDIRECTS table", () => {
  it("maps /processes to #/ (home org chart)", () => {
    assert.equal(REDIRECTS["/processes"], "#/");
  });

  it("maps /server to #/scheduler", () => {
    assert.equal(REDIRECTS["/server"], "#/scheduler");
  });

  it("maps /setup to #/settings (legacy)", () => {
    assert.equal(REDIRECTS["/setup"], "#/settings");
  });

  it("maps /memory to #/ (home org chart)", () => {
    assert.equal(REDIRECTS["/memory"], "#/");
  });

  it("maps /assets to #/ (home org chart)", () => {
    assert.equal(REDIRECTS["/assets"], "#/");
  });

  it("maps /activity-report to #/activity", () => {
    assert.equal(REDIRECTS["/activity-report"], "#/activity");
  });

  it("maps /logs to #/activity/logs", () => {
    assert.equal(REDIRECTS["/logs"], "#/activity/logs");
  });

  it("maps /users to #/settings/users", () => {
    assert.equal(REDIRECTS["/users"], "#/settings/users");
  });
});

describe("resolveRedirect", () => {
  it("redirects #/processes path to #/", () => {
    assert.equal(resolveRedirect("/processes"), "#/");
  });

  it("redirects nested /processes/* paths to #/", () => {
    assert.equal(resolveRedirect("/processes/anything"), "#/");
  });

  it("redirects /server and nested paths to #/scheduler", () => {
    assert.equal(resolveRedirect("/server"), "#/scheduler");
    assert.equal(resolveRedirect("/server/anything"), "#/scheduler");
  });

  it("redirects /setup and nested paths to #/settings", () => {
    assert.equal(resolveRedirect("/setup"), "#/settings");
    assert.equal(resolveRedirect("/setup/foo"), "#/settings");
  });

  it("redirects /memory and nested paths to #/", () => {
    assert.equal(resolveRedirect("/memory"), "#/");
    assert.equal(resolveRedirect("/memory/anything"), "#/");
  });

  it("redirects /assets and nested paths to #/", () => {
    assert.equal(resolveRedirect("/assets"), "#/");
    assert.equal(resolveRedirect("/assets/anything"), "#/");
  });

  it("redirects /activity-report to #/activity", () => {
    assert.equal(resolveRedirect("/activity-report"), "#/activity");
  });

  it("redirects /logs and nested paths to #/activity/logs", () => {
    assert.equal(resolveRedirect("/logs"), "#/activity/logs");
    assert.equal(resolveRedirect("/logs/anything"), "#/activity/logs");
  });

  it("redirects /users and nested paths to #/settings/users", () => {
    assert.equal(resolveRedirect("/users"), "#/settings/users");
    assert.equal(resolveRedirect("/users/anything"), "#/settings/users");
  });

  it("returns null for non-redirect paths (bare /animas handled in handleRoute)", () => {
    // /animas is not in REDIRECTS (prefix would break detail routes);
    // exact #/animas → #/ is handled in handleRoute.
    assert.equal(resolveRedirect("/animas"), null);
    assert.equal(resolveRedirect("/chat"), null);
    assert.equal(resolveRedirect("/activity"), null);
    assert.equal(resolveRedirect("/settings"), null);
    assert.equal(resolveRedirect("/animas/sakura/process"), null);
  });
});

describe("resolveRouteMatch (subPath decomposition)", () => {
  const keys = ["/", "/chat", "/animas", "/activity", "/settings"];

  it("exact match yields empty subPath", () => {
    const m = resolveRouteMatch("/animas", keys);
    assert.deepEqual(m, { route: "/animas", subPath: "", navPath: "/animas" });
  });

  it("decomposes #/animas/<name> into subPath name", () => {
    const m = resolveRouteMatch("/animas/sakura", keys);
    assert.equal(m.route, "/animas");
    assert.equal(m.subPath, "sakura");
    assert.equal(m.navPath, "/animas");
  });

  it("decomposes #/animas/<name>/<tab> keeping slash in subPath", () => {
    const m = resolveRouteMatch("/animas/sakura/process", keys);
    assert.equal(m.route, "/animas");
    assert.equal(m.subPath, "sakura/process");
    assert.equal(m.navPath, "/animas");
  });

  it("decodes URI-encoded name segments", () => {
    const m = resolveRouteMatch("/animas/" + encodeURIComponent("さくら") + "/overview", keys);
    assert.equal(m.subPath, "さくら/overview");
  });

  it("picks longest matching prefix", () => {
    const keys2 = ["/a", "/a/b", "/animas"];
    const m = resolveRouteMatch("/a/b/c", keys2);
    assert.equal(m.route, "/a/b");
    assert.equal(m.subPath, "c");
  });

  it("returns null when no route matches", () => {
    assert.equal(resolveRouteMatch("/unknown", keys), null);
  });
});

describe("parseAnimaSubPath", () => {
  it("returns null name and overview for empty subPath", () => {
    assert.deepEqual(parseAnimaSubPath(""), { name: null, tab: "overview" });
    assert.deepEqual(parseAnimaSubPath(null), { name: null, tab: "overview" });
    assert.deepEqual(parseAnimaSubPath(undefined), { name: null, tab: "overview" });
  });

  it("defaults tab to overview when only name is present", () => {
    assert.deepEqual(parseAnimaSubPath("sakura"), {
      name: "sakura",
      tab: "overview",
    });
  });

  it("parses name and tab from two segments", () => {
    assert.deepEqual(parseAnimaSubPath("sakura/process"), {
      name: "sakura",
      tab: "process",
    });
    assert.deepEqual(parseAnimaSubPath("sakura/overview"), {
      name: "sakura",
      tab: "overview",
    });
  });
});

describe("bare /animas redirect and detail nav highlight (source contract)", () => {
  const routerSource = readFileSync(ROUTER_PATH, "utf8");

  it("redirects exact /animas path to home in handleRoute", () => {
    assert.match(routerSource, /path\s*===\s*["']\/animas["']/);
    assert.match(routerSource, /location\.hash\s*=\s*["']#\/["']/);
  });

  it("highlights Home nav for anima detail routes", () => {
    assert.match(routerSource, /matched\.route\s*===\s*["']\/animas["']/);
    assert.match(routerSource, /navPath\s*=\s*["']\/["']/);
  });
});
