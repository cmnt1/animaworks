import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const staticDir = resolve(__dirname, "../../../server/static");

// index.html maps only "/shared/" into the versioned base path. Any other absolute
// specifier resolves against the site root, which is outside the /app prefix behind
// the reverse proxy, so the whole page module fails to load.
const MAPPED_PREFIXES = ["/shared/"];
const IMPORT_RE = /(?:\bfrom\s*|\bimport\s*\(\s*|^\s*import\s+)["'](\/[^"']*)["']/gm;

function jsFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return name === "vendor" ? [] : jsFiles(full);
    return /\.m?js$/.test(name) ? [full] : [];
  });
}

describe("static module import paths", () => {
  it("uses only importmap-mapped absolute specifiers", () => {
    const offenders = [];
    for (const file of jsFiles(staticDir)) {
      for (const match of readFileSync(file, "utf8").matchAll(IMPORT_RE)) {
        const spec = match[1];
        if (!MAPPED_PREFIXES.some((prefix) => spec.startsWith(prefix))) {
          offenders.push(`${relative(staticDir, file)}: ${spec}`);
        }
      }
    }
    assert.deepEqual(offenders, []);
  });
});
