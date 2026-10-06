/**
 * timeline-replay.js — replay timeline events through the active office
 * renderer, or show them in the shared message popup.
 */

import { showMessage as showMessagePopup } from "./message-popup.js";
import { resolvePersons } from "./timeline-dom.js";

let _highlightAnima = null;
let _getActiveRenderer = null;
let _highlightImport = null;
let _clearHighlightTimer = null;

export function ensureHighlightFns() {
  if (_highlightAnima) return Promise.resolve();
  if (!_highlightImport) {
    _highlightImport = import("./office-renderer.js")
      .then((mod) => {
        _highlightAnima = mod.highlightAnima;
        _getActiveRenderer = mod.getActiveRenderer;
      })
      .catch(() => {
        // Timeline replay can still open shared message details without a renderer.
      });
  }
  return _highlightImport;
}

function highlightTemporarily(name) {
  if (!_highlightAnima || !name) return;
  if (_clearHighlightTimer) clearTimeout(_clearHighlightTimer);
  _highlightAnima(name);
  _clearHighlightTimer = setTimeout(() => {
    _highlightAnima?.(null);
    _clearHighlightTimer = null;
  }, 3000);
}

/**
 * Replay a timeline event in the currently selected office renderer.
 *
 * @param {object} event
 * @param {HTMLElement} el
 * @param {{ interactionManager: object|null }} ctx
 */
export async function replayEvent(event, el, ctx) {
  const { type, anima, meta } = event;
  const { interactionManager } = ctx;

  el.classList.add("replaying");
  setTimeout(() => el.classList.remove("replaying"), 2000);
  await ensureHighlightFns();

  switch (type) {
    case "message":
    case "dm_received":
    case "dm_sent": {
      const persons = resolvePersons(event);
      if (_getActiveRenderer?.() === "3d" && interactionManager && persons.from && persons.to) {
        interactionManager.showMessageEffect(persons.from, persons.to, persons.text);
      } else if (persons.from || persons.to) {
        highlightTemporarily(persons.from || persons.to);
      }
      if (meta?.message_id) showMessagePopup(meta.message_id);
      break;
    }

    case "chat":
    case "message_received":
    case "response_sent":
    case "board":
    case "channel_read":
    case "channel_post":
    case "heartbeat":
    case "heartbeat_start":
    case "heartbeat_end":
    case "heartbeat_reflection":
    case "cron":
    case "cron_executed":
    default:
      highlightTemporarily(anima);
      break;
  }
}
