const VALID_RENDERERS = new Set(["pixel", "3d"]);
const VALID_VIEWS = new Set(["office", "org", "battle"]);

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
 * @returns {"office"|"org"|"battle"}
 */
export function normalizeWorkspaceView(view, fallback = "office") {
  if (view === "3d" || view === "office") return "office";
  if (view === "org" || view === "battle") return view;
  if (fallback === "3d" || fallback === "office") return "office";
  if (VALID_VIEWS.has(fallback)) return fallback;
  return "office";
}

/**
 * Resolve the workspace shell view without touching browser globals.
 * Valid URL views override saved preferences; an old saved `3d` view is
 * migrated to `office` by the same normalizer used by the shell.
 *
 * @param {string|URLSearchParams} search
 * @param {string|null|undefined} storedView
 * @param {string} [fallback="office"]
 * @returns {{ view: "office"|"org"|"battle", source: "url"|"localStorage"|"default" }}
 */
export function selectWorkspaceView(search = "", storedView = null, fallback = "office") {
  const params = search instanceof URLSearchParams
    ? search
    : new URLSearchParams(typeof search === "string" ? search : "");
  const urlView = params.get("view");
  if (VALID_VIEWS.has(urlView)) {
    return { view: urlView, source: "url" };
  }

  if (storedView === "3d" || VALID_VIEWS.has(storedView)) {
    return {
      view: normalizeWorkspaceView(storedView, fallback),
      source: "localStorage",
    };
  }

  return { view: normalizeWorkspaceView(fallback), source: "default" };
}
