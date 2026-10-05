/* ── API Helper ────────────────────────────── */

import { createLogger } from "../shared/logger.js";
import { basePath } from "../shared/base-path.js";

const logger = createLogger("api");

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
export async function api(path, opts = {}) {
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
      // Redirect to login screen on auth failure
      if (logErrors) logger.warn("Unauthorized, redirecting to login", { url: path });
      window.location.hash = "";
      window.location.reload();
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
