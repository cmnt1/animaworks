/* ── API Helper ────────────────────────────── */

import { createLogger } from "../shared/logger.js";
import { basePath } from "../shared/base-path.js";

const logger = createLogger("api");
const _inflightRequests = new Map();

function _prefixed(path) {
  if (basePath && path.startsWith(`${basePath}/`)) return path;
  if (basePath && path.startsWith("/")) return `${basePath}${path}`;
  return path;
}

/**
 * Send a base-path aware JSON API request.
 *
 * Use `rawResponse` for binary or HEAD requests. `throwOnHttpError: false` and
 * `acceptedStatuses` are available when the caller needs to inspect statuses.
 */
function _inflightKey(path, opts) {
  const method = String(opts.method || "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD") return null;
  if (method === "GET" && opts.rawResponse) return null;
  if (opts.signal) return null;

  const url = _prefixed(path);
  const headers = [...new Headers(opts.headers || {}).entries()].sort(([a], [b]) => a.localeCompare(b));
  return JSON.stringify([
    method,
    url,
    opts.cache || "no-store",
    headers,
    Boolean(opts.rawResponse),
    Boolean(opts.redirectOnUnauthorized ?? true),
    Boolean(opts.logErrors ?? true),
    Boolean(opts.throwOnHttpError ?? true),
    [...(opts.acceptedStatuses || [])].sort(),
  ]);
}

export function api(path, opts = {}) {
  const key = _inflightKey(path, opts);
  if (key && _inflightRequests.has(key)) return _inflightRequests.get(key);

  const request = _sendRequest(path, opts);
  if (key) {
    _inflightRequests.set(key, request);
    request.then(
      () => { if (_inflightRequests.get(key) === request) _inflightRequests.delete(key); },
      () => { if (_inflightRequests.get(key) === request) _inflightRequests.delete(key); },
    );
  }
  return request;
}

async function _sendRequest(path, opts = {}) {
  const {
    redirectOnUnauthorized = true,
    logErrors = true,
    acceptedStatuses = [],
    rawResponse = false,
    throwOnHttpError = true,
    ...fetchOpts
  } = opts;
  try {
    fetchOpts.credentials = "same-origin";
    if (!fetchOpts.cache) fetchOpts.cache = "no-store";
    const res = await fetch(_prefixed(path), fetchOpts);

    if (res.status === 401 && redirectOnUnauthorized) {
      // Redirect to the top-level login screen on auth failure. Reloading the
      // current page loops on sub-apps like /workspace/ that start from a
      // saved username and hit 401 again on every load.
      if (logErrors) logger.warn("Unauthorized, redirecting to login", { url: path });
      window.location.href = `${basePath}/`;
      throw new Error("Unauthorized");
    }

    if (!res.ok && throwOnHttpError && !acceptedStatuses.includes(res.status)) {
      if (logErrors) logger.error("API request failed", { url: path, status: res.status, statusText: res.statusText });
      const payload = await res.json().catch(() => ({}));
      const detail = payload?.detail;
      const message = (typeof detail === "string" ? detail : detail?.message) || payload?.message || payload?.error;
      const error = new Error(message || `API ${res.status}: ${res.statusText}`);
      error.status = res.status;
      error.payload = payload;
      throw error;
    }
    return rawResponse ? res : res.json();
  } catch (err) {
    if (logErrors && err.message && !err.message.startsWith("API ") && err.message !== "Unauthorized" && !err.status) {
      logger.error("Network error", { url: path, error: err.message });
    }
    throw err;
  }
}
