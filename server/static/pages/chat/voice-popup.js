/**
 * Voice conversation popup — bustup + hands-free (VAD) voice chat overlay.
 * Opened by long-pressing an anima tab on the chat page.
 */
import { voiceManager } from "../../modules/voice.js";
import { destroyVoiceUI } from "../../modules/voice-ui.js";
import { BustupAnimator } from "./bustup-animator.js";
import { escapeHtml } from "../../modules/state.js";
import { t } from "/shared/i18n.js";

const NEUTRAL_RESET_MS = 10_000;
const VALID_EXPRESSIONS = new Set([
  "neutral", "smile", "laugh", "troubled", "surprised", "thinking", "embarrassed",
]);

/** @type {null | {
 *   overlay: HTMLElement,
 *   animaName: string,
 *   onClose: (() => void) | null,
 *   listeners: Array<[string, Function]>,
 *   neutralTimer: ReturnType<typeof setTimeout> | null,
 *   els: Record<string, HTMLElement>,
 *   animator: BustupAnimator | null,
 *   responseText: string,
 *   closed: boolean,
 * }} */
let _session = null;

/**
 * @param {string} animaName
 * @param {{ onClose?: () => void }} [opts]
 */
export function openVoicePopup(animaName, opts = {}) {
  if (!animaName) return;
  if (_session) closeVoicePopup();

  // Release chat-input VoiceUI so it does not share the singleton VoiceManager.
  destroyVoiceUI();

  const overlay = document.createElement("div");
  overlay.className = "voice-popup-overlay";
  overlay.id = "voicePopupOverlay";
  overlay.innerHTML = `
    <div class="voice-popup-card" role="dialog" aria-modal="true" aria-label="${escapeHtml(t("voice.popup_title"))}">
      <button type="button" class="voice-popup-close" aria-label="${escapeHtml(t("common.aria_close"))}">&times;</button>
      <div class="voice-popup-header">
        <span class="voice-popup-name">${escapeHtml(animaName)}</span>
        <span class="voice-popup-status" data-vp="status">${escapeHtml(t("voice.popup_connecting"))}</span>
      </div>
      <div class="voice-popup-bustup-wrap">
        <div class="voice-popup-bustup-rig" data-vp="rig"></div>
        <div class="voice-popup-subtitle" data-vp="subtitle" hidden></div>
      </div>
      <div class="voice-popup-captions">
        <div class="voice-popup-transcript" data-vp="transcript"></div>
        <div class="voice-popup-response" data-vp="response"></div>
      </div>
      <div class="voice-popup-error" data-vp="error" hidden></div>
      <div class="voice-toolbar voice-popup-toolbar">
        <div class="voice-toolbar-status">
          <span class="voice-rec-indicator" data-vp="rec" style="display:none"></span>
          <span class="voice-tts-indicator" data-vp="tts" style="display:none"></span>
          <span class="voice-thinking-indicator" data-vp="thinking" style="display:none">${escapeHtml(t("chat.thinking"))}</span>
        </div>
        <div class="voice-toolbar-controls">
          <button type="button" class="voice-mode-toggle" data-vp="mode" title="${escapeHtml(t("voice.mode_toggle"))}">AUTO</button>
          <input type="range" class="voice-volume-slider" data-vp="volume" min="0" max="100" value="80">
        </div>
      </div>
    </div>
  `;

  const q = (sel) => overlay.querySelector(`[data-vp="${sel}"]`);
  const els = {
    status: q("status"),
    rig: q("rig"),
    transcript: q("transcript"),
    subtitle: q("subtitle"),
    response: q("response"),
    error: q("error"),
    rec: q("rec"),
    tts: q("tts"),
    thinking: q("thinking"),
    mode: q("mode"),
    volume: q("volume"),
    closeBtn: overlay.querySelector(".voice-popup-close"),
  };

  // 疑似Live2D: 静止画フレーム + CSS/JS。フレームが無い表情は静的bustupへフォールバック。
  const animator = new BustupAnimator(els.rig, animaName);

  _session = {
    overlay,
    animaName,
    onClose: typeof opts.onClose === "function" ? opts.onClose : null,
    listeners: [],
    neutralTimer: null,
    els,
    animator,
    responseText: "",
    closed: false,
  };

  document.body.appendChild(overlay);
  requestAnimationFrame(() => overlay.classList.add("visible"));

  els.closeBtn.addEventListener("click", () => closeVoicePopup());
  els.mode.addEventListener("click", () => {
    const next = voiceManager.mode === "ptt" ? "vad" : "ptt";
    voiceManager.setMode(next);
    els.mode.textContent = next === "ptt" ? "PTT" : "AUTO";
  });
  els.volume.addEventListener("input", () => {
    voiceManager.setVolume(parseInt(els.volume.value, 10) / 100);
  });
  // Tap the bustup to barge-in: in VAD mode the mic ignores speech while the
  // anima is talking (its own TTS would trigger the VAD), so a tap is the
  // reliable interrupt. Gated on playback so an idle tap can't wipe an
  // in-progress user utterance server-side.
  els.rig.addEventListener("click", () => {
    if (voiceManager.isTTSPlaying) voiceManager.interrupt();
  });

  document.addEventListener("keydown", _onKeyDown);

  animator.setExpression("neutral");
  _bindVoiceEvents();
  _startSession(animaName);
}

export function closeVoicePopup() {
  if (!_session || _session.closed) return;
  _session.closed = true;

  const { overlay, listeners, neutralTimer, onClose, animator } = _session;

  if (animator) animator.destroy();

  for (const [event, handler] of listeners) {
    voiceManager.off(event, handler);
  }
  if (neutralTimer) clearTimeout(neutralTimer);
  document.removeEventListener("keydown", _onKeyDown);

  voiceManager.disconnect();

  overlay.classList.remove("visible");
  overlay.classList.add("hiding");
  const remove = () => overlay.remove();
  overlay.addEventListener("transitionend", remove, { once: true });
  // Fallback if transitionend does not fire
  setTimeout(remove, 400);

  _session = null;
  onClose?.();
}

export function isVoicePopupOpen() {
  return Boolean(_session && !_session.closed);
}

function _onKeyDown(e) {
  if (e.key === "Escape") {
    e.preventDefault();
    closeVoicePopup();
  }
}

function _bind(event, handler) {
  voiceManager.on(event, handler);
  _session.listeners.push([event, handler]);
}

function _bindVoiceEvents() {
  const { els } = _session;

  _bind("connected", () => {
    if (!_session) return;
    els.status.textContent = t("voice.popup_connected");
  });
  _bind("disconnected", () => {
    if (!_session) return;
    els.status.textContent = t("voice.popup_disconnected");
    els.rec.style.display = "none";
    els.tts.style.display = "none";
    els.thinking.style.display = "none";
    if (_session.animator) _session.animator.stopLipsync();
  });
  _bind("recordingStart", () => {
    if (!_session) return;
    els.rec.style.display = "";
    els.status.textContent = t("voice.popup_listening");
  });
  _bind("recordingStop", () => {
    if (!_session) return;
    els.rec.style.display = "none";
  });
  _bind("ttsStart", () => {
    if (!_session) return;
    els.tts.style.display = "";
    els.status.textContent = t("voice.popup_speaking");
    if (_session.animator) {
      _session.animator.startLipsync(() => voiceManager.ttsRMS);
    }
  });
  _bind("ttsDone", () => {
    if (!_session) return;
    if (!voiceManager.isTTSPlaying) els.tts.style.display = "none";
  });
  _bind("playbackEnd", () => {
    if (!_session) return;
    els.tts.style.display = "none";
    if (_session.animator) _session.animator.stopLipsync();
  });
  _bind("interrupted", () => {
    if (!_session) return;
    els.tts.style.display = "none";
    els.subtitle.hidden = true;
    els.status.textContent = t("voice.popup_connected");
    if (_session.animator) _session.animator.stopLipsync();
  });
  _bind("caption", ({ text }) => {
    if (!_session) return;
    if (text) {
      els.subtitle.textContent = text;
      els.subtitle.hidden = false;
    } else {
      els.subtitle.hidden = true;
    }
  });
  _bind("transcript", ({ text }) => {
    if (!_session || !text) return;
    els.transcript.textContent = text;
  });
  // Live committed prefix while the user is still speaking (streaming STT).
  // The final "transcript" event overwrites it, so display-only is enough.
  _bind("transcriptPartial", ({ text }) => {
    if (!_session || !text) return;
    els.transcript.textContent = text + "…";
  });
  _bind("responseStart", () => {
    if (!_session) return;
    _session.responseText = "";
    els.response.textContent = "";
  });
  _bind("responseText", ({ text }) => {
    if (!_session || !text) return;
    _session.responseText += text;
    // Hide emotion tags (and any partial tag still streaming) from the caption.
    els.response.textContent = _session.responseText
      .replace(/<!--[\s\S]*?(?:-->|$)/g, "")
      .trimEnd();
  });
  _bind("responseDone", ({ emotion }) => {
    if (!_session) return;
    if (emotion) _applyEmotion(emotion);
    _scheduleNeutralReset();
  });
  _bind("emotion", ({ emotion }) => {
    if (!_session) return;
    _applyEmotion(emotion);
  });
  _bind("thinkingStatus", (thinking) => {
    if (!_session) return;
    els.thinking.style.display = thinking ? "" : "none";
  });
  _bind("error", ({ message }) => {
    if (!_session) return;
    console.warn("[VoicePopup]", message);
    const msg = String(message || "");
    // "Microphone error: ..." also covers non-permission failures (e.g. worklet
    // load) — only permission-shaped errors get the mic-denied guidance.
    if (/permission|notallowed|denied|拒否/i.test(msg)) {
      _showMicDenied();
    } else {
      _showError(msg);
    }
  });
  _bind("modeChange", ({ mode }) => {
    if (!_session) return;
    els.mode.textContent = mode === "ptt" ? "PTT" : "AUTO";
  });
}

async function _startSession(animaName) {
  if (!_session || _session.closed) return;
  const { els } = _session;
  els.status.textContent = t("voice.popup_connecting");

  try {
    await voiceManager.connect(animaName);
  } catch (err) {
    if (!_session || _session.closed) return;
    els.status.textContent = t("voice.popup_connect_failed");
    _showError(t("voice.popup_connect_failed"));
    return;
  }
  if (!_session || _session.closed) return;

  // Default to hands-free VAD. Force-toggle if already vad so VAD restarts after disconnect.
  if (voiceManager.mode === "vad") {
    voiceManager.setMode("ptt");
  }
  voiceManager.setMode('vad');
  els.mode.textContent = "AUTO";

  // Surface mic-permission failures (VAD init may only warn).
  if (!navigator.mediaDevices?.getUserMedia) {
    // http origin etc. — permission state is irrelevant, the API itself is absent.
    _showError(t("voice.popup_mic_insecure"));
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((tr) => tr.stop());
  } catch (err) {
    if (!_session || _session.closed) return;
    _showMicDenied(err);
  }

  if (!_session || _session.closed) return;
  if (voiceManager.isConnected) {
    els.status.textContent = t("voice.popup_connected");
  }
}

function _showMicDenied(err) {
  // Keep the raw error name visible — NotAllowedError (site/OS permission),
  // NotFoundError (no device), NotReadableError (device busy) need different fixes.
  const name = err?.name ? ` [${err.name}]` : "";
  _showError(t("voice.popup_mic_denied") + name);
  // Guide user toward PTT (still needs mic) or close.
  if (voiceManager.mode === "vad") {
    voiceManager.setMode("ptt");
    if (_session) _session.els.mode.textContent = "PTT";
  }
}

function _showError(msg) {
  if (!_session) return;
  const { error } = _session.els;
  error.hidden = false;
  error.textContent = msg;
}

function _applyEmotion(emotion) {
  if (!_session || !emotion) return;
  const expr = String(emotion).toLowerCase();
  if (!VALID_EXPRESSIONS.has(expr)) return;
  _session.animator?.setExpression(expr);
}

function _scheduleNeutralReset() {
  if (!_session) return;
  if (_session.neutralTimer) clearTimeout(_session.neutralTimer);
  _session.neutralTimer = setTimeout(() => {
    if (!_session) return;
    _session.animator?.setExpression("neutral");
    _session.neutralTimer = null;
  }, NEUTRAL_RESET_MS);
}
