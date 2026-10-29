// ── "Waiting for your reply" list: which notifications still need an answer, and jump to them ──
import { waitingItems } from "../../modules/anima-presence.js";

const MAX_OLDER_PAGES = 20;
let _popover = null;
let _offDoc = null;

function _timeLabel(ts) {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  const today = new Date();
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  return d.toDateString() === today.toDateString() ? hm : `${d.getMonth() + 1}/${d.getDate()} ${hm}`;
}

export function closeWaitingList() {
  _popover?.remove();
  _popover = null;
  _offDoc?.();
  _offDoc = null;
}

/** Find a message row by timestamp, loading older history pages until it appears. */
export async function jumpToMessage(fctx, ts) {
  const messages = fctx.$("chatPageMessages");
  if (!messages || !ts) return false;
  const find = () => messages.querySelector(`[data-message-ts="${CSS.escape(ts)}"]`);
  let el = find();
  for (let i = 0; !el && i < MAX_OLDER_PAGES; i += 1) {
    const hs = fctx.state.manager?.getHistoryState?.(fctx.state.selectedAnima, fctx.state.selectedThreadId);
    if (hs && hs.hasMore === false) break;
    await fctx.controllers.renderer.loadOlderMessages?.();
    el = find();
  }
  if (!el) return false;
  const row = el.closest(".chat-line") || el;
  fctx.controllers.renderer.markUserDetached?.();
  row.scrollIntoView({ block: "center", behavior: "smooth" });
  row.classList.remove("chat-line--flash");
  void row.offsetWidth;
  row.classList.add("chat-line--flash");
  setTimeout(() => row.classList.remove("chat-line--flash"), 2400);
  return true;
}

/**
 * Open the list next to `anchor` for `anima`.
 * @param {{ anchor: HTMLElement, anima: string, getFocused: () => any, t: Function, escapeHtml: Function }} opts
 */
export function openWaitingList({ anchor, anima, getFocused, t, escapeHtml }) {
  closeWaitingList();
  const items = waitingItems(anima);
  const pop = document.createElement("div");
  pop.className = "chat-waiting-list";
  pop.setAttribute("role", "dialog");
  pop.setAttribute("aria-label", t("chat.presence.waiting_list_title", { name: anima }));
  const rows = items.length
    ? items.map((it) => `<li><button type="button" class="chat-waiting-item" data-ts="${escapeHtml(it.ts)}">`
      + `<span class="chat-waiting-time">${escapeHtml(_timeLabel(it.ts))}</span>`
      + `<span class="chat-waiting-text">${escapeHtml(it.subject || it.preview || "")}</span></button></li>`).join("")
    : `<li class="chat-waiting-empty">${escapeHtml(t("chat.presence.waiting_list_empty"))}</li>`;
  pop.innerHTML = `<div class="chat-waiting-head">${escapeHtml(t("chat.presence.waiting_list_title", { name: anima }))}`
    + `<span class="chat-waiting-count">${items.length}</span></div><ul>${rows}</ul>`;
  document.body.appendChild(pop);

  const r = anchor.getBoundingClientRect();
  const width = Math.min(340, window.innerWidth - 24);
  pop.style.width = `${width}px`;
  pop.style.left = `${Math.max(12, Math.min(r.left, window.innerWidth - width - 12))}px`;
  pop.style.top = `${Math.min(r.bottom + 6, window.innerHeight - 80)}px`;
  _popover = pop;

  pop.addEventListener("click", async (e) => {
    const btn = e.target.closest(".chat-waiting-item");
    if (!btn) return;
    const focused = getFocused();
    if (!focused) return;
    closeWaitingList();
    const fctx = focused.ctx;
    if (fctx.state.selectedAnima !== anima) await fctx.controllers.anima.openOrSelectAnima(anima);
    await jumpToMessage(fctx, btn.dataset.ts);
  });

  const onDoc = (e) => {
    if (_popover && !_popover.contains(e.target) && e.target !== anchor && !anchor.contains(e.target)) closeWaitingList();
  };
  const onKey = (e) => { if (e.key === "Escape") closeWaitingList(); };
  setTimeout(() => document.addEventListener("pointerdown", onDoc), 0);
  document.addEventListener("keydown", onKey);
  _offDoc = () => {
    document.removeEventListener("pointerdown", onDoc);
    document.removeEventListener("keydown", onKey);
  };
}
