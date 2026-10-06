const VALID_RENDERERS = new Set(["pixel", "3d"]);
const VALID_VIEWS = new Set(["office", "org"]);

/**
 * Resolve the renderer preference without touching browser globals.
 * URL parameters intentionally win over saved preferences so a support URL
 * can switch renderer and then persist that choice for later visits.
 *
 * @param {string|URLSearchParams} search
 * @param {string|null|undefined} storedRenderer
 * @returns {{ renderer: "pixel"|"3d", source: "url"|"localStorage"|"default" }}
 */
export function selectOfficeRenderer(search = "", storedRenderer = null) {
  const params = search instanceof URLSearchParams
    ? search
    : new URLSearchParams(typeof search === "string" ? search : "");
  const urlRenderer = params.get("renderer");
  if (VALID_RENDERERS.has(urlRenderer)) {
    return { renderer: urlRenderer, source: "url" };
  }
  if (VALID_RENDERERS.has(storedRenderer)) {
    return { renderer: storedRenderer, source: "localStorage" };
  }
  return { renderer: "pixel", source: "default" };
}

/**
 * Normalize the workspace shell view while migrating the old `3d` value.
 * Invalid or missing values use the caller's normalized fallback.
 *
 * @param {string|null|undefined} view
 * @param {string} [fallback="office"]
 * @returns {"office"|"org"}
 */
export function normalizeWorkspaceView(view, fallback = "office") {
  if (view === "3d" || view === "office") return "office";
  if (view === "org") return "org";
  if (fallback === "org") return "org";
  if (VALID_VIEWS.has(fallback)) return fallback;
  return "office";
}
