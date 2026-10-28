/** Browser glue for presence toasts: shared queue, DOM stack, open-chat action. */
import { t } from "/shared/i18n.js";
import { presence } from "./anima-presence.js";
import { createToastQueue, mountToastStack, shouldShowToast } from "./presence-toast.js";
import { faceUrl } from "../shared/chat/emotion-face.js";
import { attachFaceFallback } from "../pages/chat/pane-head.js";

let _queue = null;

export function openAnimaChat(anima, detail = {}) {
  presence.requestOpen(anima);
  if (!(window.location.hash || "").startsWith("#/chat")) {
    window.location.hash = "#/chat";
  }
  document.dispatchEvent(new CustomEvent("aw:open-anima", { detail: { anima, ...detail } }));
}

function _ensureQueue() {
  if (_queue) return _queue;
  let render = () => {};
  _queue = createToastQueue({ onChange: (v) => render(v) });
  render = mountToastStack({
    doc: document,
    queue: _queue,
    faceUrl: (a, e) => faceUrl(a, e, "S"),
    emotionFor: (a) => presence.emotionFor(a),
    t,
    onReply: (anima, item) => openAnimaChat(anima, { replyTo: item.replyTo || null }),
  });
  const stack = document.getElementById("awToastStack");
  if (stack) attachFaceFallback(stack, () => "");
  return _queue;
}

/** Show a toast unless that anima's conversation is already on screen. */
export function notifyAnimaToast({ kind, anima, body, priority = "normal", replyTo = null }) {
  if (!shouldShowToast({ kind, anima, visibleAnimas: presence.visibleSet() })) return false;
  _ensureQueue().push({ anima, kind, body, priority, replyTo });
  return true;
}

let _wired = false;
/** Reply-finished toasts for conversations that are not on screen. */
export function wireReplyToasts() {
  if (_wired) return;
  _wired = true;
  document.addEventListener("aw:anima-activity", (ev) => {
    const d = ev.detail;
    if (d?.phase !== "done" || !d.anima) return;
    notifyAnimaToast({
      kind: "reply",
      anima: d.anima,
      body: t("chat.presence.toast_reply_body"),
    });
  });
}
