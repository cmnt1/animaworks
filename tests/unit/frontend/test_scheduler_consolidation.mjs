import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const source = readFileSync(
  resolve(process.cwd(), "server/static/pages/scheduler-page.js"),
  "utf8",
);

const progressFnSource = source.match(
  /export function consolidationProgressText\(job\)\s*\{[\s\S]*?\n\}/,
)?.[0];
assert.ok(progressFnSource);
const consolidationProgressText = new Function(
  `${progressFnSource.replace("export ", "")}; return consolidationProgressText;`,
)();

test("scheduler restores the memory consolidation management panel", () => {
  const modelIdx = source.indexOf('id="serverConsolidationModel"');
  const panelIdx = source.indexOf('id="serverConsolidationContent"');
  const schedulerIdx = source.indexOf('id="schedulerPageContent"');

  assert.ok(modelIdx >= 0);
  assert.ok(panelIdx >= 0);
  assert.ok(schedulerIdx >= 0);
  assert.ok(modelIdx < panelIdx);
  assert.ok(panelIdx < schedulerIdx);
  assert.match(source, /\/api\/system\/config/);
  assert.match(source, /\/api\/system\/consolidation\/model/);
  assert.match(source, /consolidationRouteSelect/);
  assert.match(source, /consolidationProviderSelect/);
  assert.match(source, /consolidationModelSelect/);
  assert.match(source, /\/api\/system\/consolidation\/status/);
  assert.match(source, /data-consolidation-run/);
  assert.match(source, /\/api\/system\/consolidation\/catchup/);
  assert.match(source, /onEvent\("system\.consolidation_status"/);
});

test("weekly progress is rendered as current/total", () => {
  assert.equal(
    consolidationProgressText({
      running: true,
      progress_current: 5,
      progress_total: 15,
    }),
    "5/15",
  );
  assert.equal(consolidationProgressText({ running: false, progress_current: 5, progress_total: 15 }), "");
  assert.equal(consolidationProgressText({ running: true }), "");
});
