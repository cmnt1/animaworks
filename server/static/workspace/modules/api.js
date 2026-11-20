// ── API Client ──────────────────────
// Thin API client for all workspace REST endpoints.

import { api } from "../../modules/api.js";
import { basePath } from "/shared/base-path.js";

const BASE = basePath;

function request(path, opts = {}) {
  return api(path, opts);
}

function post(path, body) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function put(path, body) {
  return request(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function del(path) {
  return request(path, { method: "DELETE" });
}

// ── Anima ──────────────────────

export function fetchAnimas() {
  return request("/api/animas");
}

// ── System ──────────────────────

export function fetchSystemStatus() {
  return request("/api/system/status");
}

export function fetchSharedUsers() {
  return request("/api/shared/users");
}

function reloadSystem() {
  return post("/api/system/reload", {});
}

function triggerHeartbeat(name) {
  return post(`/api/animas/${encodeURIComponent(name)}/trigger`, {});
}

export function fetchSnsSearchEntries() {
  return request("/api/sns-search");
}

export function createSnsSearchEntry(entry) {
  return post("/api/sns-search", entry);
}

export function updateSnsSearchEntry(id, entry) {
  return put(`/api/sns-search/${encodeURIComponent(id)}`, entry);
}

export function deleteSnsSearchEntry(id) {
  return del(`/api/sns-search/${encodeURIComponent(id)}`);
}

// ── Assets ──────────────────────

export function assetUrl(name, filename) {
  return `${BASE}/api/animas/${encodeURIComponent(name)}/assets/${encodeURIComponent(filename)}`;
}

export function fetchAssetMetadata(name) {
  return request(`/api/animas/${encodeURIComponent(name)}/assets/metadata`);
}

/**
 * Check if an asset exists by issuing a HEAD request.
 * Returns the URL if it exists, or null otherwise.
 */
export async function probeAsset(name, filename) {
  const url = assetUrl(name, filename);
  try {
    const res = await api(url, {
      method: "HEAD",
      cache: "default",
      rawResponse: true,
      redirectOnUnauthorized: false,
      throwOnHttpError: false,
      logErrors: false,
    });
    return res.ok ? url : null;
  } catch {
    return null;
  }
}

// ── Messages ──────────────────────

export async function fetchMessage(messageId) {
  return request(`/api/messages/${encodeURIComponent(messageId)}`);
}
