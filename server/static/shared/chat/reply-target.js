// Per-pane reply target state and the ordinary-chat quote prefix.
export function getReplyTarget(state) {
  return state?.replyTarget || null;
}

export function setReplyTarget(state, target) {
  if (!state) return null;
  state.replyTarget = target && typeof target === "object" ? { ...target } : null;
  return state.replyTarget;
}

export function clearReplyTarget(state) {
  if (!state) return null;
  const target = state.replyTarget || null;
  state.replyTarget = null;
  return target;
}

export function quoteReplyMessage(text, target) {
  if (!target || target.type === "notification") return String(text || "");
  const quoted = String(target.text || "").replace(/\s+/g, " ").trim().slice(0, 80);
  return quoted ? `> ${quoted}\n\n${String(text || "")}` : String(text || "");
}
