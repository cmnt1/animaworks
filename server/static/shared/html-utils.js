/**
 * Shared HTML escaping and timestamp formatting helpers for static modules.
 */

const HTML_ESCAPES = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

/** Escape text for safe insertion into HTML content. */
export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => HTML_ESCAPES[char]);
}

/** Escape a value for safe insertion into a quoted HTML attribute. */
export function escapeAttr(value) {
  return escapeHtml(value);
}

/** Format a timestamp as HH:MM using the Japanese locale. */
export function timeStr(isoOrTs) {
  if (!isoOrTs) return "--:--";
  const date = new Date(isoOrTs);
  if (Number.isNaN(date.getTime())) return "--:--";
  return date.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" });
}

/** Format the current local time as HH:MM:SS using the Japanese locale. */
export function nowTimeStr() {
  return new Date().toLocaleTimeString("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/**
 * Format a timestamp with smart granularity: HH:MM today, MM/DD HH:MM this
 * year, and YYYY/MM/DD HH:MM for earlier years.
 */
export function smartTimestamp(isoOrTs) {
  if (!isoOrTs) return "";
  const date = new Date(isoOrTs);
  if (Number.isNaN(date.getTime())) return "";

  const now = new Date();
  const time = date.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" });
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  if (sameDay) return time;

  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  if (date.getFullYear() === now.getFullYear()) return `${month}/${day} ${time}`;
  return `${date.getFullYear()}/${month}/${day} ${time}`;
}
