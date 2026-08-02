/**
 * Unit tests for Anima page process integration helpers and process tab.
 *
 * Run with: node --test tests/unit/frontend/test_animas_page.mjs
 *
 * Modules under test import absolute "/shared/..." paths and browser-only
 * deps; we load rewritten sources via data: URLs with stubs.
 */

import { describe, it, beforeEach, mock } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const STATIC = resolve(__dirname, "../../../server/static");

// ── Minimal DOM ──────────────────────────────

class MockEl {
  constructor(tag = "div") {
    this.tagName = String(tag).toUpperCase();
    this.className = "";
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.style = {};
    this._listeners = {};
    this.parentNode = null;
    this._innerHTML = "";
    this.textContent = "";
    this.disabled = false;
    this.id = "";
    this.value = "";
    const self = this;
    this.classList = {
      toggle(cls, force) {
        const parts = new Set(self.className.split(/\s+/).filter(Boolean));
        if (force === true) parts.add(cls);
        else if (force === false) parts.delete(cls);
        else if (parts.has(cls)) parts.delete(cls);
        else parts.add(cls);
        self.className = [...parts].join(" ");
      },
      contains(cls) {
        return self.className.split(/\s+/).includes(cls);
      },
      add(cls) {
        const parts = new Set(self.className.split(/\s+/).filter(Boolean));
        parts.add(cls);
        self.className = [...parts].join(" ");
      },
      remove(cls) {
        const parts = new Set(self.className.split(/\s+/).filter(Boolean));
        parts.delete(cls);
        self.className = [...parts].join(" ");
      },
    };
  }

  set innerHTML(html) {
    this._innerHTML = String(html ?? "");
    this.children = [];
  }

  get innerHTML() {
    return this._innerHTML;
  }

  setAttribute(n, v) {
    this.attributes[n] = String(v);
    if (n.startsWith("data-")) this.dataset[n.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(v);
  }

  getAttribute(n) {
    return this.attributes[n] ?? null;
  }

  appendChild(c) {
    c.parentNode = this;
    this.children.push(c);
    return c;
  }

  remove() {
    if (this.parentNode) {
      const i = this.parentNode.children.indexOf(this);
      if (i >= 0) this.parentNode.children.splice(i, 1);
      this.parentNode = null;
    }
  }

  querySelectorAll(sel) {
    // Search in innerHTML string for matching class buttons
    if (sel.startsWith(".")) {
      const cls = sel.slice(1).split(/[\s.>]/)[0];
      const out = [];
      const re = new RegExp(
        `<button\\b([^>]*class="[^"]*\\b${cls}\\b[^"]*"[^>]*)>`,
        "gi",
      );
      let m;
      while ((m = re.exec(this._innerHTML)) !== null) {
        const btn = new MockEl("button");
        const attrs = m[1];
        const nameM = attrs.match(/data-name="([^"]*)"/);
        if (nameM) btn.dataset.name = nameM[1];
        const classM = attrs.match(/class="([^"]*)"/);
        if (classM) btn.className = classM[1];
        btn.parentNode = this;
        out.push(btn);
      }
      // Also search children
      for (const c of this.children) {
        out.push(...c.querySelectorAll(sel));
      }
      return out;
    }
    if (sel.startsWith("#")) {
      const id = sel.slice(1);
      if (this.id === id) return [this];
      const out = [];
      for (const c of this.children) out.push(...c.querySelectorAll(sel));
      return out;
    }
    return [];
  }

  querySelector(sel) {
    return this.querySelectorAll(sel)[0] || null;
  }

  addEventListener(type, fn) {
    if (!this._listeners[type]) this._listeners[type] = [];
    this._listeners[type].push(fn);
  }

  closest() {
    return null;
  }
}

const _byId = new Map();

globalThis.document = {
  createElement(tag) {
    return new MockEl(tag);
  },
  getElementById(id) {
    return _byId.get(id) || null;
  },
  body: new MockEl("body"),
  querySelector() {
    return null;
  },
};

globalThis.window = globalThis;
globalThis.confirm = () => true;

// ── Load pure helpers from modules/animas.js (stubbed deps) ──

function loadAnimasHelpers() {
  const path = resolve(STATIC, "modules/animas.js");
  let source = readFileSync(path, "utf8");

  // Strip all imports; inject stubs
  source = source.replace(/^import\s+.+;?\s*$/gm, "");
  const preamble = `
    const state = { animas: [], selectedAnima: null, animaDetail: null, activeMemoryTab: "episodes" };
    const dom = {};
    const escapeHtml = (s) => String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
    const t = (k, vars) => {
      if (!vars) return k;
      return k + ":" + JSON.stringify(vars);
    };
    let _apiImpl = async () => { throw new Error("api not mocked"); };
    const api = (...args) => _apiImpl(...args);
    const loadMemoryTab = async () => {};
    const animaHashColor = () => "#000";
    const bustupCandidates = () => [];
    const resolveCachedAvatar = async () => null;
    export function __setApi(fn) { _apiImpl = fn; }
  `;
  source = preamble + "\n" + source;

  const url =
    "data:text/javascript;base64," + Buffer.from(source, "utf8").toString("base64");
  return import(url);
}

const helpers = await loadAnimasHelpers();

describe("process display helpers (modules/animas.js)", () => {
  it("healthIndicatorHtml returns green for running", () => {
    const html = helpers.healthIndicatorHtml("running", 0);
    assert.match(html, /#22c55e/);
    assert.match(html, /processes\.health_ok/);
  });

  it("healthIndicatorHtml returns red for error", () => {
    const html = helpers.healthIndicatorHtml("error", 0);
    assert.match(html, /#ef4444/);
  });

  it("healthIndicatorHtml returns amber when missed pings > 0", () => {
    const html = helpers.healthIndicatorHtml("running", 2);
    assert.match(html, /#f59e0b/);
  });

  it("statusBadgeHtml marks running as success", () => {
    const html = helpers.statusBadgeHtml("running");
    assert.match(html, /status-badge/);
    assert.match(html, /success/);
    assert.match(html, /running/);
  });

  it("statusBadgeHtml marks error as error", () => {
    const html = helpers.statusBadgeHtml("error");
    assert.match(html, /error/);
  });

  it("processActionButtonsHtml shows Heartbeat/Interrupt/Restart/Stop when running", () => {
    const html = helpers.processActionButtonsHtml("sakura", "running");
    assert.match(html, /process-trigger-btn/);
    assert.match(html, /process-interrupt-btn/);
    assert.match(html, /process-restart-btn/);
    assert.match(html, /process-stop-btn/);
    assert.match(html, /data-name="sakura"/);
  });

  it("processActionButtonsHtml shows Start when stopped", () => {
    const html = helpers.processActionButtonsHtml("sakura", "stopped");
    assert.match(html, /process-start-btn/);
    assert.doesNotMatch(html, /process-stop-btn/);
  });

  it("formatUptime formats hours and minutes", () => {
    const s = helpers.formatUptime(3660);
    assert.match(s, /animas\.uptime_hm/);
  });
});

describe("fetchAnimasWithProcessStatus merge", () => {
  it("merges process map onto anima list", async () => {
    helpers.__setApi(async (path) => {
      if (path === "/api/animas") {
        return [
          { name: "sakura", status: "offline", pid: null },
          { name: "yuki", status: "stopped", pid: null },
        ];
      }
      if (path === "/api/system/status") {
        return {
          processes: {
            sakura: {
              status: "running",
              pid: 1234,
              uptime_sec: 100,
              missed_pings: 0,
            },
          },
        };
      }
      throw new Error("unexpected " + path);
    });

    const rows = await helpers.fetchAnimasWithProcessStatus();
    assert.equal(rows.length, 2);
    assert.equal(rows[0].name, "sakura");
    assert.equal(rows[0].status, "running");
    assert.equal(rows[0].pid, 1234);
    assert.equal(rows[1].name, "yuki");
    assert.equal(rows[1].status, "stopped");
  });

  it("falls back to process entries when anima list is empty but processes exist", async () => {
    helpers.__setApi(async (path) => {
      if (path === "/api/animas") return [];
      if (path === "/api/system/status") {
        return { processes: { solo: { status: "running", pid: 9 } } };
      }
      throw new Error("unexpected " + path);
    });

    const rows = await helpers.fetchAnimasWithProcessStatus();
    assert.equal(rows.length, 1);
    assert.equal(rows[0].name, "solo");
    assert.equal(rows[0].status, "running");
  });
});

describe("status + org kebab helpers (modules/animas.js)", () => {
  it("integrates health + status + uptime; PID only in title", () => {
    const html = helpers.buildAnimaListStatusHtml({
      status: "running",
      missed_pings: 0,
      uptime_sec: 120,
      pid: 42,
    });
    assert.match(html, /anima-list-status--success/);
    assert.match(html, /#22c55e/);
    assert.match(html, /running/);
    assert.match(html, /title="PID: 42"/);
    assert.doesNotMatch(html, />42</);
  });

  it("uses warning tone when missed_pings > 0", () => {
    const html = helpers.buildAnimaListStatusHtml({
      status: "running",
      missed_pings: 2,
      uptime_sec: 60,
      pid: 1,
    });
    assert.match(html, /anima-list-status--warning/);
    assert.match(html, /#f59e0b/);
  });

  it("splitProcessActionButtons isolates Heartbeat from menu ops", () => {
    const { triggerHtml, menuHtml, hasMenu } = helpers.splitProcessActionButtons(
      "sakura",
      "running",
    );
    assert.match(triggerHtml, /process-trigger-btn/);
    assert.doesNotMatch(triggerHtml, /process-stop-btn/);
    assert.match(menuHtml, /process-stop-btn/);
    assert.doesNotMatch(menuHtml, /process-trigger-btn/);
    assert.equal(hasMenu, true);
  });

  it("buildOrgCardKebabHtml includes open-detail + process actions", () => {
    const html = helpers.buildOrgCardKebabHtml("sakura", "running");
    assert.match(html, /anima-list-kebab-btn/);
    assert.match(html, /org-card-open-detail/);
    assert.match(html, /animas\.open_detail/);
    assert.match(html, /process-trigger-btn/);
    assert.match(html, /process-stop-btn/);
    assert.match(html, /data-href="#\/animas\/sakura"/);
  });

  it("buildOrgCardKebabHtml shows Start when stopped", () => {
    const html = helpers.buildOrgCardKebabHtml("sakura", "stopped");
    assert.match(html, /process-start-btn/);
    assert.doesNotMatch(html, /process-trigger-btn/);
  });

  it("mergeNodeWithProcess overlays process fields", () => {
    const merged = helpers.mergeNodeWithProcess(
      { name: "sakura", status: "offline", speciality: "PM" },
      { sakura: { status: "running", pid: 7, uptime_sec: 10 } },
    );
    assert.equal(merged.name, "sakura");
    assert.equal(merged.status, "running");
    assert.equal(merged.pid, 7);
    assert.equal(merged.speciality, "PM");
  });

  it("collectOrgChartNames walks the tree", () => {
    const names = helpers.collectOrgChartNames([
      { name: "ceo", children: [{ name: "a" }, { name: "b", children: [{ name: "c" }] }] },
    ]);
    assert.deepEqual([...names].sort(), ["a", "b", "c", "ceo"]);
  });

  it("findUnlistedAnimas returns process names missing from chart", () => {
    const chart = new Set(["sakura"]);
    const unlisted = helpers.findUnlistedAnimas(
      { sakura: { status: "running" }, ghost: { status: "stopped" }, solo: {} },
      chart,
    );
    assert.deepEqual(unlisted, ["ghost", "solo"]);
  });
});

describe("process tab module", () => {
  it("renders process detail card for a single anima", async () => {
    const animaName = "sakura";
    const proc = {
      name: animaName,
      status: "running",
      pid: 99,
      uptime_sec: 3600,
      restart_count: 1,
      missed_pings: 0,
      last_ping: "2026-07-20T00:00:00Z",
    };

    const content = new MockEl("div");
    content.id = "animaProcessTabContent";
    _byId.set("animaProcessTabContent", content);

    const status = proc.status;
    const html = `
      <div class="card">
        <table class="data-table">
          <tr><th>processes.table_health</th><td>${helpers.healthIndicatorHtml(status, 0)}</td></tr>
          <tr><th>processes.table_anima</th><td>${animaName}</td></tr>
          <tr><th>processes.table_pid</th><td>${proc.pid}</td></tr>
          <tr><th>processes.table_status</th><td>${helpers.statusBadgeHtml(status)}</td></tr>
          <tr><th>processes.table_actions</th><td class="process-actions">${helpers.processActionButtonsHtml(animaName, status)}</td></tr>
        </table>
      </div>
    `;
    content.innerHTML = html;

    assert.match(content.innerHTML, /processes\.table_health/);
    assert.match(content.innerHTML, /sakura/);
    assert.match(content.innerHTML, /99/);
    assert.match(content.innerHTML, /process-trigger-btn/);
    assert.match(content.innerHTML, /status-badge success/);

    helpers.bindProcessActionButtons(content, { onReload: () => {} });
    const triggers = content.querySelectorAll(".process-trigger-btn");
    assert.equal(triggers.length, 1);
    assert.equal(triggers[0].dataset.name, "sakura");
  });

  it("exports render/destroy contract for anima-tabs/process.js", () => {
    const source = readFileSync(
      resolve(STATIC, "pages/anima-tabs/process.js"),
      "utf8",
    );
    assert.match(source, /export function render\(/);
    assert.match(source, /export function destroy\(/);
    assert.match(source, /animaName/);
    assert.match(source, /setInterval/);
    assert.match(source, /clearInterval/);
    assert.match(source, /healthIndicatorHtml/);
    assert.match(source, /processActionButtonsHtml/);
  });
});

describe("animas.js page structure (source contract)", () => {
  const pageSource = readFileSync(resolve(STATIC, "pages/animas.js"), "utf8");

  it("uses page-tabs and parseAnimaSubPath for detail tabs", () => {
    assert.match(pageSource, /createPageTabs/);
    assert.match(pageSource, /parseAnimaSubPath/);
    assert.match(pageSource, /anima-tabs\//);
    assert.match(pageSource, /tab_overview|overview/);
    assert.match(pageSource, /process/);
    assert.match(pageSource, /memory/);
  });

  it("restores the dedicated list while retaining detail routes", () => {
    assert.match(pageSource, /_renderList/);
    assert.match(pageSource, /_loadListContent/);
    assert.match(pageSource, /_loadListAvatars/);
    assert.match(pageSource, /fetchAnimasWithProcessStatus/);
    assert.match(pageSource, /setInterval\(_loadListContent,\s*10000\)/);
  });

  it("shows the foreground and background model columns", () => {
    assert.match(pageSource, /animas\.table_fr_model/);
    assert.match(pageSource, /animas\.table_bg_model/);
    assert.match(pageSource, /_shortModel\(p\.model\)/);
    assert.match(pageSource, /_shortModel\(p\.background_model\)/);
  });

  it("navigates with #/animas/<name>/<tab> hash", () => {
    assert.match(pageSource, /#\/animas\//);
    assert.match(pageSource, /_navigateAnimas/);
    assert.match(pageSource, /buildAnimaDetailHash/);
  });

  it("has anima switcher that keeps current tab", () => {
    assert.match(pageSource, /animasSwitcher/);
    assert.match(pageSource, /_populateAnimaSwitcher/);
    assert.match(pageSource, /fetchAnimasList/);
  });

  it("back button returns to the Anima management list", () => {
    assert.match(pageSource, /animasBackBtn/);
    assert.match(pageSource, /_navigateAnimas\(null\)/);
  });
});

describe("buildAnimaDetailHash", () => {
  function loadBuildHash() {
    const path = resolve(STATIC, "pages/animas.js");
    let source = readFileSync(path, "utf8");
    source = source.replace(/^import\s+.+;?\s*$/gm, "");
    // Keep only the pure helper (avoid side-effectful module body needing DOM)
    const match = source.match(
      /export function buildAnimaDetailHash\([\s\S]*?\n\}/,
    );
    assert.ok(match, "buildAnimaDetailHash not found");
    const body =
      match[0].replace(/^export /, "") +
      "\nexport { buildAnimaDetailHash };\n";
    const url =
      "data:text/javascript;base64," +
      Buffer.from(body, "utf8").toString("base64");
    return import(url + "#hash-" + Math.random());
  }

  it("returns list hash when name is empty", async () => {
    const { buildAnimaDetailHash } = await loadBuildHash();
    assert.equal(buildAnimaDetailHash(null), "#/animas");
    assert.equal(buildAnimaDetailHash(""), "#/animas");
    assert.equal(buildAnimaDetailHash(undefined), "#/animas");
  });

  it("omits overview tab segment", async () => {
    const { buildAnimaDetailHash } = await loadBuildHash();
    assert.equal(buildAnimaDetailHash("sakura"), "#/animas/sakura");
    assert.equal(buildAnimaDetailHash("sakura", "overview"), "#/animas/sakura");
  });

  it("keeps non-overview tab and encodes name", async () => {
    const { buildAnimaDetailHash } = await loadBuildHash();
    assert.equal(
      buildAnimaDetailHash("sakura", "memory"),
      "#/animas/sakura/memory",
    );
    assert.equal(
      buildAnimaDetailHash("sakura", "process"),
      "#/animas/sakura/process",
    );
    assert.equal(
      buildAnimaDetailHash("さくら", "schedule"),
      `#/animas/${encodeURIComponent("さくら")}/schedule`,
    );
  });
});

describe("router no longer registers /processes", () => {
  it("does not import processes.js and redirects the legacy list to Anima management", () => {
    const source = readFileSync(resolve(STATIC, "modules/router.js"), "utf8");
    assert.doesNotMatch(source, /pages\/processes\.js/);
    assert.match(source, /REDIRECTS/);
    assert.match(source, /"\/processes"\s*:\s*"#\/animas"/);
  });
});
