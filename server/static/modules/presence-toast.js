/**
 * Presence toasts — face + name + one line + [reply] [later].
 *
 * Pure queue/decision logic is exported for tests; the DOM renderer only uses
 * injected dependencies, so this module imports nothing.
 */

export const MAX_TOASTS = 3;
export const AUTO_DISMISS_MS = 8000;

/**
 * Whether a toast should appear.
 * kind: "notification" (お知らせ) | "reply" (chat reply finished elsewhere).
 * Never shown while that anima's conversation is on screen.
 */
export function shouldShowToast({ kind, anima, visibleAnimas }) {
  if (!anima) return false;
  if (kind !== "notification" && kind !== "reply") return false;
  const visible = visibleAnimas instanceof Set ? visibleAnimas : new Set(visibleAnimas || []);
  return !visible.has(anima);
}

export function createToastQueue({
  max = MAX_TOASTS,
  autoMs = AUTO_DISMISS_MS,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
  onChange = () => {},
} = {}) {
  let seq = 0;
  /** @type {Array<{id:number, anima:string, kind:string, body:string, priority:string, timer:any}>} */
  let items = [];

  function _emit() { onChange(api.view()); }

  const api = {
    push({ anima, kind = "notification", body = "", priority = "normal" }) {
      // One toast per anima+kind: a newer one replaces the older.
      const dup = items.find((i) => i.anima === anima && i.kind === kind);
      if (dup) api.dismiss(dup.id, true);
      const id = ++seq;
      const item = { id, anima, kind, body, priority, timer: null };
      if (priority !== "urgent") {
        item.timer = setTimer(() => api.dismiss(id), autoMs);
      }
      items.push(item);
      _emit();
      return id;
    },

    dismiss(id, silent = false) {
      const idx = items.findIndex((i) => i.id === id);
      if (idx < 0) return false;
      if (items[idx].timer != null) clearTimer(items[idx].timer);
      items.splice(idx, 1);
      if (!silent) _emit();
      return true;
    },

    clear() {
      for (const i of items) if (i.timer != null) clearTimer(i.timer);
      items = [];
      _emit();
    },

    /** Newest `max` toasts are shown (urgent ones are never pushed out); rest counted. */
    view() {
      const urgent = items.filter((i) => i.priority === "urgent");
      const normal = items.filter((i) => i.priority !== "urgent");
      const room = Math.max(0, max - urgent.length);
      const shownNormal = normal.slice(Math.max(0, normal.length - room));
      const shown = items.filter((i) => urgent.includes(i) || shownNormal.includes(i));
      return {
        shown: shown.map(({ timer, ...rest }) => rest),
        overflow: items.length - shown.length,
      };
    },

    get size() { return items.length; },
  };
  return api;
}

/**
 * Mount a toast stack. deps: { doc, queue, faceUrl(anima, emotion), emotionFor(anima),
 * t(key, vars), onReply(anima), kindLabel(kind) }.
 */
export function mountToastStack({ doc, queue, faceUrl, emotionFor, t, onReply }) {
  let stack = doc.getElementById("awToastStack");
  if (!stack) {
    stack = doc.createElement("div");
    stack.id = "awToastStack";
    stack.className = "aw-ptoast-stack";
    stack.setAttribute("aria-live", "polite");
    doc.body.appendChild(stack);
  }

  function render({ shown, overflow }) {
    stack.textContent = "";
    for (const it of shown) {
      const card = doc.createElement("div");
      card.className = `aw-ptoast aw-ptoast-${it.kind} priority-${it.priority}`;
      card.dataset.anima = it.anima;

      const img = doc.createElement("img");
      img.className = "aw-ptoast-face";
      img.alt = "";
      img.dataset.face = it.anima;
      img.src = faceUrl(it.anima, it.kind === "notification" ? "troubled" : emotionFor(it.anima));
      card.appendChild(img);

      const t1 = doc.createElement("div");
      t1.className = "aw-ptoast-t1";
      const b = doc.createElement("b");
      b.textContent = it.anima;
      t1.appendChild(b);
      t1.appendChild(doc.createTextNode(" · " + t(it.kind === "notification"
        ? "chat.presence.toast_kind_waiting" : "chat.presence.toast_kind_reply")));
      card.appendChild(t1);

      const t2 = doc.createElement("div");
      t2.className = "aw-ptoast-t2";
      t2.textContent = it.body;
      card.appendChild(t2);

      const tb = doc.createElement("div");
      tb.className = "aw-ptoast-tb";
      const go = doc.createElement("button");
      go.type = "button";
      go.className = "go";
      go.textContent = t("chat.presence.toast_reply");
      go.addEventListener("click", () => { queue.dismiss(it.id); onReply(it.anima, it); });
      const later = doc.createElement("button");
      later.type = "button";
      later.textContent = t("chat.presence.toast_later");
      later.addEventListener("click", () => queue.dismiss(it.id));
      tb.appendChild(go);
      tb.appendChild(later);
      card.appendChild(tb);
      stack.appendChild(card);
    }
    if (overflow > 0) {
      const more = doc.createElement("div");
      more.className = "aw-ptoast-more";
      more.textContent = t("chat.presence.toast_more", { count: overflow });
      stack.appendChild(more);
    }
  }
  return render;
}
