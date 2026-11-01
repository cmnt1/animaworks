// Pure helpers for the left rail (no DOM / browser-only imports).

/**
 * Order: the focused pane's open tabs first, then the remaining animas.
 * Names in `hidden` are left out unless they are in `keep` (e.g. waiting for a reply).
 */
export function orderRailAnimas(animas, tabNames, hidden = new Set(), keep = new Set()) {
  const enabled = (animas || []).filter((a) => a && a.name && a.enabled !== false
    && (!hidden.has(a.name) || keep.has(a.name)));
  const byName = new Map(enabled.map((a) => [a.name, a]));
  const out = [];
  for (const n of tabNames || []) {
    if (byName.has(n)) { out.push(byName.get(n)); byName.delete(n); }
  }
  for (const a of enabled) if (byName.has(a.name)) out.push(a);
  return out;
}

/** Badge: awaiting wins over the unread count. */
export function railBadge(entry) {
  if (entry.awaitingHuman) return { kind: "wait", text: "!" };
  if (entry.unread > 0) return { kind: "unread", text: entry.unread > 99 ? "99+" : String(entry.unread) };
  return null;
}

/** Animas that can be put back on the rail: enabled and hidden, in the server's order. */
export function hiddenRailAnimas(animas, hidden) {
  return (animas || []).filter((a) => a && a.name && a.enabled !== false && hidden.has(a.name));
}
