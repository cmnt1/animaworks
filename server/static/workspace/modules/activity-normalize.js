/**
 * activity-normalize.js — shared activity event normalization helpers.
 */

function firstString(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.length > 0) return value;
  }
  return "";
}

/**
 * Normalize API/WS event shape: animas→anima, timestamp→ts, ensure id.
 * @param {object} raw
 * @returns {object}
 */
export function normalizeActivityEvent(raw) {
  const evt = { ...(raw || {}) };
  if (Array.isArray(evt.animas) && !evt.anima) {
    evt.anima = evt.animas[0] ?? null;
  }
  if (evt.timestamp && !evt.ts) {
    evt.ts = evt.timestamp;
  }
  if (!evt.id) {
    evt.id = evt.ts || String(Date.now() + Math.random());
  }
  return evt;
}

/**
 * Resolve actor, target, text, and routing metadata from API and WS event shapes.
 * `meta` wins over top-level fields because it is the more specific event payload.
 *
 * @param {object} event
 * @returns {{ from: string, to: string, text: string, intent: string, fromType: string }}
 */
export function resolveEventPersons(event) {
  const evt = event || {};
  const meta = evt.meta || {};
  return {
    from: firstString(meta.from_person, evt.from_person, evt.from, evt.anima),
    to: firstString(meta.to_person, evt.to_person, evt.to),
    text: resolveEventText(evt),
    intent: firstString(meta.intent, evt.intent),
    fromType: firstString(meta.from_type, evt.from_type),
  };
}

/**
 * Resolve display text from API and WS event shapes.
 * @param {object} event
 * @returns {string}
 */
export function resolveEventText(event) {
  const evt = event || {};
  const meta = evt.meta || {};
  return firstString(meta.text, evt.content, evt.summary);
}

/**
 * Resolve channel name from API and WS event shapes.
 * @param {object} event
 * @returns {string}
 */
export function resolveEventChannel(event) {
  const evt = event || {};
  const meta = evt.meta || {};
  return firstString(meta.channel, evt.channel);
}

/**
 * Get timestamp in ms for an event.
 * @param {object} event
 * @returns {number}
 */
export function eventTimeMs(event) {
  const ts = event?.ts || event?.timestamp;
  return ts ? new Date(ts).getTime() : 0;
}
