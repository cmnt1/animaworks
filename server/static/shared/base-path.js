// ── Base Path ──────────────────────────────────
// Single source of truth for the deployment base path.
// Injected server-side as a <meta> tag; falls back to "" (root deploy).
//
// Usage:
//   import { basePath } from '/shared/base-path.js';
//   fetch(`${basePath}/api/animas`);
//   const wsUrl = `${proto}//${location.host}${basePath}/ws`;

function _resolve() {
  const meta = document.querySelector('meta[name="aw-base-path"]');
  if (meta) return meta.content;
  return "";
}

export const basePath = _resolve();
