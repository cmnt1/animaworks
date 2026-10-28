/**
 * Full-page voice call UI for the chat page.
 * The audio transport and session stay in VoiceManager; this module owns only
 * the call view, transcript, and persisted call summary.
 */
import { voiceManager } from "../../modules/voice.js";
import { destroyVoiceUI } from "../../modules/voice-ui.js";
import { BustupAnimator } from "./bustup-animator.js";
import { api } from "../../modules/api.js";
import { bustupCandidates, resolveCachedAvatar } from "../../modules/avatar-resolver.js";
import { t } from "/shared/i18n.js";

const VALID_EXPRESSIONS = new Set([
  "neutral", "smile", "laugh", "troubled", "surprised", "thinking", "embarrassed",
]);
const WAITING_HINT_MS = 2000;

let _activeCall = null;

export function formatElapsedTime(totalSeconds) {
  const seconds = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function _element(tag, className = "", text = null) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== null) el.textContent = text;
  return el;
}

function _append(parent, tag, className = "", text = null) {
  const el = _element(tag, className, text);
  parent.appendChild(el);
  return el;
}

function _setSvgIcon(host, path) {
  host.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="${path}"/></svg>`;
}

function _cleanResponseText(value) {
  return String(value || "").replace(/<!--[\s\S]*?(?:-->|$)/g, "").trim();
}

/**
 * @param {string} animaName
 * @param {{
 *   container?: HTMLElement,
 *   threadId?: string,
 *   onClose?: () => void,
 *   onRecord?: (record: object) => void,
 *   voice?: object,
 *   animatorFactory?: (container: HTMLElement, animaName: string) => object,
 *   postCall?: (animaName: string, record: object) => Promise<unknown>,
 *   now?: () => number,
 *   setInterval?: typeof setInterval,
 *   clearInterval?: typeof clearInterval,
 *   setTimeout?: typeof setTimeout,
 *   clearTimeout?: typeof clearTimeout,
 *   removeVoiceUI?: () => void,
 * }} [opts]
 * @returns {CallScreen | null}
 */
export function openCallScreen(animaName, opts = {}) {
  if (!animaName) return null;
  if (_activeCall) _activeCall.finish();

  const container = opts.container
    || document.querySelector(".chat-page-layout")
    || document.body;
  const call = new CallScreen(animaName, container, opts);
  _activeCall = call;
  call.start();
  return call;
}

export class CallScreen {
  constructor(animaName, container, opts = {}) {
    this.animaName = animaName;
    this.container = container;
    this.threadId = opts.threadId || "default";
    this.voice = opts.voice || voiceManager;
    this.animatorFactory = opts.animatorFactory || ((host, name) => new BustupAnimator(host, name));
    this.postCall = opts.postCall || ((name, record) => api(
      `/api/animas/${encodeURIComponent(name)}/conversation/calls`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(record),
      },
    ));
    this.now = opts.now || (() => Date.now());
    this.setInterval = opts.setInterval || globalThis.setInterval.bind(globalThis);
    this.clearInterval = opts.clearInterval || globalThis.clearInterval.bind(globalThis);
    this.setTimeout = opts.setTimeout || globalThis.setTimeout.bind(globalThis);
    this.clearTimeout = opts.clearTimeout || globalThis.clearTimeout.bind(globalThis);
    this.removeVoiceUI = opts.removeVoiceUI || destroyVoiceUI;
    this.onClose = typeof opts.onClose === "function" ? opts.onClose : null;
    this.onRecord = typeof opts.onRecord === "function" ? opts.onRecord : null;

    this.startedAt = new Date(this.now()).toISOString();
    this.connectedAt = null;
    this.finished = false;
    this.minimized = false;
    this.muted = false;
    this.captionsVisible = true;
    this.thinking = false;
    this.expression = "neutral";
    this.responseText = "";
    this.lastResponse = "";
    this.liveUserText = "";
    this.transcript = [];
    this.listeners = [];
    this.clockTimer = null;
    this.waitTimer = null;
    this.els = this._buildView();
    this.animators = [];
    this._onKeyDown = this._onKeyDown.bind(this);
  }

  _buildView() {
    const root = _element("section", "aw-call-screen is-ringing");
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    root.setAttribute("aria-label", t("chat.call.screen_title", { name: this.animaName }));

    const feed = _append(root, "div", "aw-call-feed");
    const mainRig = _append(feed, "div", "aw-call-main-rig");
    _append(root, "div", "aw-call-shade aw-call-shade-top");
    _append(root, "div", "aw-call-shade aw-call-shade-bottom");

    const top = _append(root, "header", "aw-call-top");
    const name = _append(top, "span", "aw-call-name", this.animaName);
    const time = _append(top, "span", "aw-call-time", t("chat.call.ringing"));
    const minimize = _append(top, "button", "aw-call-return", t("chat.call.return_to_chat"));
    minimize.type = "button";

    const ring = _append(root, "div", "aw-call-ring-center");
    const ringAvatar = _append(ring, "img", "aw-call-ring-avatar");
    ringAvatar.alt = this.animaName;
    const ringLabel = _append(ring, "div", "", t("chat.call.calling", { name: this.animaName }));

    const self = _append(root, "div", "aw-call-self-tile");
    _append(self, "span", "aw-call-self-avatar", (t("chat.call.you").charAt(0) || "?").toUpperCase());
    _append(self, "span", "", t("chat.call.camera_off"));
    self.hidden = true;

    const work = _append(root, "div", "aw-call-work-chip");
    const dots = _append(work, "span", "aw-call-dots");
    for (let i = 0; i < 3; i += 1) _append(dots, "i");
    const workText = _append(work, "span", "", t("chat.call.working"));
    work.hidden = true;

    const captions = _append(root, "div", "aw-call-captions");
    const captionUser = _append(captions, "div", "aw-call-caption aw-call-caption-user");
    const captionAnima = _append(captions, "div", "aw-call-caption aw-call-caption-anima");
    const listen = _append(captions, "div", "aw-call-listen");
    const bars = _append(listen, "span", "aw-call-listen-bars");
    for (let i = 0; i < 4; i += 1) _append(bars, "i");
    _append(listen, "span", "", t("chat.call.listening"));
    listen.hidden = true;
    const transcriptButton = _append(captions, "button", "aw-call-transcript-open", t("chat.call.open_transcript"));
    transcriptButton.type = "button";

    const error = _append(root, "div", "aw-call-error");
    error.hidden = true;

    const controls = _append(root, "div", "aw-call-controls");
    const mute = this._control(controls, "mute", t("chat.call.mute"), "M18.5 12a6.5 6.5 0 0 1-13 0H3a9 9 0 0 0 8 8.94V23h2v-2.06A9 9 0 0 0 21 12zM12 16a4 4 0 0 0 4-4V5a4 4 0 0 0-8 0v7a4 4 0 0 0 4 4z");
    const captionsToggle = this._control(controls, "captions", t("chat.call.captions"), "M19 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm-8 7H9v-1H7v4h2v-1h2v2H6V8h5zm7 0h-2v-1h-2v4h2v-1h2v2h-7V8h7z");
    const end = this._control(controls, "end", t("chat.call.end"), "M12 9c-1.6 0-3.15.25-4.6.72v3.1a1 1 0 0 1-.56.9 11.5 11.5 0 0 0-2.66 1.85 1 1 0 0 1-1.41 0L.29 13.08a1 1 0 0 1 0-1.41A16.9 16.9 0 0 1 12 7c4.5 0 8.6 1.8 11.71 4.67a1 1 0 0 1 0 1.41l-2.48 2.49a1 1 0 0 1-1.41 0 11.3 11.3 0 0 0-2.67-1.85 1 1 0 0 1-.56-.9v-3.1A15 15 0 0 0 12 9z");
    mute.button.setAttribute("aria-pressed", "false");
    captionsToggle.button.setAttribute("aria-pressed", "true");
    captionsToggle.button.classList.add("is-active");

    const pip = _element("div", "aw-call-pip");
    pip.setAttribute("role", "button");
    pip.setAttribute("tabindex", "0");
    pip.setAttribute("aria-label", t("chat.call.return_to_call"));
    const pipRig = _append(pip, "div", "aw-call-pip-rig");
    const pipEnd = _append(pip, "button", "aw-call-pip-end");
    pipEnd.type = "button";
    pipEnd.title = t("chat.call.end");
    pipEnd.setAttribute("aria-label", t("chat.call.end"));
    _setSvgIcon(pipEnd, "M12 9c-1.6 0-3.15.25-4.6.72v3.1a1 1 0 0 1-.56.9 11.5 11.5 0 0 0-2.66 1.85 1 1 0 0 1-1.41 0L.29 13.08a1 1 0 0 1 0-1.41A16.9 16.9 0 0 1 12 7c4.5 0 8.6 1.8 11.71 4.67a1 1 0 0 1 0 1.41l-2.48 2.49a1 1 0 0 1-1.41 0 11.3 11.3 0 0 0-2.67-1.85 1 1 0 0 1-.56-.9v-3.1A15 15 0 0 0 12 9z");
    const pipFooter = _append(pip, "div", "aw-call-pip-footer");
    _append(pipFooter, "span", "aw-call-pip-name", this.animaName);
    const pipTime = _append(pipFooter, "span", "aw-call-pip-time", "0:00");
    pip.hidden = true;

    const transcriptDialog = _element("div", "aw-call-transcript-dialog");
    transcriptDialog.setAttribute("role", "dialog");
    transcriptDialog.setAttribute("aria-modal", "true");
    transcriptDialog.setAttribute("aria-label", t("chat.call.transcript_title"));
    const transcriptCard = _append(transcriptDialog, "div", "aw-call-transcript-card");
    const transcriptHeader = _append(transcriptCard, "div", "aw-call-transcript-header");
    _append(transcriptHeader, "strong", "", t("chat.call.transcript_title"));
    const transcriptClose = _append(transcriptHeader, "button", "aw-call-transcript-close", "×");
    transcriptClose.type = "button";
    transcriptClose.setAttribute("aria-label", t("common.aria_close"));
    const transcriptList = _append(transcriptCard, "ol", "aw-call-transcript-list");
    transcriptDialog.hidden = true;

    this.container.appendChild(root);
    this.container.appendChild(pip);
    this.container.appendChild(transcriptDialog);

    minimize.addEventListener("click", () => this.minimize());
    end.button.addEventListener("click", () => this.finish());
    pipEnd.addEventListener("click", (event) => {
      event.stopPropagation();
      this.finish();
    });
    pip.addEventListener("click", () => this.restore());
    pip.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        this.restore();
      }
    });
    mute.button.addEventListener("click", () => this.toggleMute());
    captionsToggle.button.addEventListener("click", () => this.toggleCaptions());
    transcriptButton.addEventListener("click", () => this.openTranscript());
    transcriptClose.addEventListener("click", () => { transcriptDialog.hidden = true; });
    transcriptDialog.addEventListener("click", (event) => {
      if (event.target === transcriptDialog) transcriptDialog.hidden = true;
    });

    return {
      root, mainRig, name, time, ring, ringAvatar, ringLabel, self, work, workText,
      captions, captionUser, captionAnima, listen, error, mute: mute.button,
      captionsToggle: captionsToggle.button, pip, pipRig, pipTime, transcriptDialog, transcriptList,
    };
  }

  _control(parent, kind, label, path) {
    const button = _append(parent, "button", `aw-call-control aw-call-control-${kind}`);
    button.type = "button";
    button.setAttribute("aria-label", label);
    const icon = _append(button, "span", "aw-call-control-icon");
    _setSvgIcon(icon, path);
    _append(button, "span", "aw-call-control-label", label);
    return { button };
  }

  start() {
    this.removeVoiceUI();
    this.mainAnimator = this.animatorFactory(this.els.mainRig, this.animaName);
    this.pipAnimator = this.animatorFactory(this.els.pipRig, this.animaName);
    this.animators = [this.mainAnimator, this.pipAnimator];
    this.setExpression("neutral");
    this._bindVoiceEvents();
    document.addEventListener("keydown", this._onKeyDown);
    this._emitActivity("call-start", t("chat.call.activity_start"));
    this._loadRingAvatar();
    this._startSession();
  }

  async _loadRingAvatar() {
    try {
      const url = await resolveCachedAvatar(this.animaName, bustupCandidates(), "S");
      if (!this.finished && url) this.els.ringAvatar.src = url;
    } catch {
      // The bustup animator still supplies the full call image when no face is available.
    }
  }

  _bind(event, handler) {
    this.voice.on(event, handler);
    this.listeners.push([event, handler]);
  }

  _bindVoiceEvents() {
    this._bind("connected", () => this._connected());
    this._bind("disconnected", () => {
      if (this.finished) return;
      this.els.listen.hidden = true;
      this.animators.forEach((animator) => animator.stopLipsync?.());
    });
    this._bind("recordingStart", () => {
      if (this.finished) return;
      this.els.listen.hidden = false;
      this.els.captionUser.hidden = true;
      this.els.captionAnima.hidden = true;
    });
    this._bind("recordingStop", () => {
      if (this.finished) return;
      this.els.listen.hidden = true;
      this.els.captionUser.hidden = false;
      this.els.captionAnima.hidden = false;
    });
    this._bind("ttsStart", () => {
      if (this.finished) return;
      this.els.listen.hidden = true;
      this.animators.forEach((animator) => animator.startLipsync?.(() => this.voice.ttsRMS));
    });
    this._bind("ttsDone", () => {});
    this._bind("playbackEnd", () => {
      if (this.finished) return;
      this.animators.forEach((animator) => animator.stopLipsync?.());
    });
    this._bind("interrupted", () => {
      if (this.finished) return;
      this.animators.forEach((animator) => animator.stopLipsync?.());
    });
    this._bind("caption", ({ text } = {}) => {
      if (this.finished || !text) return;
      this.els.captionAnima.textContent = _cleanResponseText(text);
    });
    this._bind("transcript", ({ text } = {}) => {
      if (this.finished || !text) return;
      this.liveUserText = String(text);
      this._pushTranscript("user", this.liveUserText);
      this.els.captionUser.hidden = false;
      this.els.captionUser.textContent = `${t("chat.call.you")}: ${this.liveUserText}`;
      this._showThinkingAfterDelay();
    });
    this._bind("transcriptPartial", ({ text } = {}) => {
      if (this.finished || !text) return;
      this.liveUserText = String(text);
      this.els.captionUser.hidden = false;
      this.els.captionUser.textContent = `${t("chat.call.you")}: ${this.liveUserText}…`;
    });
    this._bind("responseStart", () => {
      if (this.finished) return;
      this.responseText = "";
      this.setThinking(false);
      this.els.captionAnima.textContent = "";
      this._clearThinkingTimer();
    });
    this._bind("responseText", ({ text } = {}) => {
      if (this.finished || !text) return;
      this.responseText += text;
      this.els.captionAnima.textContent = _cleanResponseText(this.responseText);
    });
    this._bind("responseDone", ({ emotion } = {}) => {
      if (this.finished) return;
      const answer = _cleanResponseText(this.responseText);
      if (answer) {
        this.lastResponse = answer;
        this._pushTranscript("assistant", answer);
        this.els.captionAnima.textContent = answer;
      }
      this.responseText = "";
      this._clearThinkingTimer();
      this.setThinking(false);
      if (emotion) this.setExpression(emotion);
    });
    this._bind("emotion", ({ emotion } = {}) => this.setExpression(emotion));
    this._bind("thinkingStatus", (thinking) => this.setThinking(Boolean(thinking)));
    this._bind("error", () => {
      if (this.finished) return;
      this.els.error.hidden = false;
      this.els.error.textContent = t("chat.call.connect_failed");
    });
  }

  async _startSession() {
    try {
      await this.voice.connect(this.animaName);
      if (this.finished) return;
      this.voice.setMode(this.muted ? "ptt" : "vad");
    } catch {
      if (this.finished) return;
      this.els.error.hidden = false;
      this.els.error.textContent = t("chat.call.connect_failed");
    }
  }

  _connected() {
    if (this.finished || this.connectedAt !== null) return;
    this.connectedAt = this.now();
    this.els.root.classList.remove("is-ringing");
    this.els.root.classList.add("is-connected");
    this.els.ring.hidden = true;
    this.els.self.hidden = false;
    this._updateClock();
    this.clockTimer = this.setInterval(() => this._updateClock(), 1000);
  }

  _updateClock() {
    if (this.connectedAt === null) return;
    const duration = formatElapsedTime((this.now() - this.connectedAt) / 1000);
    this.els.time.textContent = duration;
    this.els.pipTime.textContent = duration;
  }

  setExpression(emotion) {
    const expression = String(emotion || "").toLowerCase();
    if (!VALID_EXPRESSIONS.has(expression)) return;
    this.expression = expression;
    this.animators.forEach((animator) => animator.setExpression?.(expression));
  }

  setThinking(value) {
    this.thinking = value;
    this.els.work.hidden = !value;
    if (value) {
      this._clearThinkingTimer();
      this.setExpression("thinking");
    } else if (this.expression === "thinking") {
      this.setExpression("neutral");
    }
  }

  _showThinkingAfterDelay() {
    this._clearThinkingTimer();
    this.waitTimer = this.setTimeout(() => {
      this.waitTimer = null;
      if (!this.finished && this.responseText === "") this.setThinking(true);
    }, WAITING_HINT_MS);
  }

  _clearThinkingTimer() {
    if (this.waitTimer !== null) {
      this.clearTimeout(this.waitTimer);
      this.waitTimer = null;
    }
  }

  _pushTranscript(speaker, text) {
    const value = String(text || "").trim();
    if (!value) return;
    const last = this.transcript[this.transcript.length - 1];
    if (last?.speaker === speaker && last.text === value) return;
    this.transcript.push({ speaker, text: value });
    this._renderTranscript();
  }

  _renderTranscript() {
    const list = this.els.transcriptList;
    list.textContent = "";
    for (const item of this.transcript) {
      const line = _append(list, "li", `aw-call-transcript-line is-${item.speaker}`);
      const speaker = item.speaker === "user" ? t("chat.call.you") : this.animaName;
      _append(line, "strong", "", `${speaker}: `);
      _append(line, "span", "", item.text);
    }
  }

  openTranscript() {
    this._renderTranscript();
    this.els.transcriptDialog.hidden = false;
  }

  minimize() {
    if (this.finished || this.minimized) return;
    this.minimized = true;
    this.els.transcriptDialog.hidden = true;
    this.els.root.hidden = true;
    this.els.pip.hidden = false;
  }

  restore() {
    if (this.finished || !this.minimized) return;
    this.minimized = false;
    this.els.root.hidden = false;
    this.els.pip.hidden = true;
  }

  toggleMute() {
    if (this.finished) return;
    this.muted = !this.muted;
    if (this.muted) {
      this.voice.stopRecording?.();
      this.voice.setMode("ptt");
    } else {
      this.voice.setMode("vad");
    }
    this.els.mute.setAttribute("aria-pressed", String(this.muted));
    this.els.mute.classList.toggle("is-active", this.muted);
    this.els.mute.setAttribute("aria-label", t(this.muted ? "chat.call.unmute" : "chat.call.mute"));
    const label = this.els.mute.children?.[1];
    if (label) label.textContent = t(this.muted ? "chat.call.unmute" : "chat.call.mute");
  }

  toggleCaptions() {
    if (this.finished) return;
    this.captionsVisible = !this.captionsVisible;
    this.els.root.classList.toggle("captions-hidden", !this.captionsVisible);
    this.els.captionsToggle.setAttribute("aria-pressed", String(this.captionsVisible));
    this.els.captionsToggle.classList.toggle("is-active", this.captionsVisible);
  }

  _emitActivity(phase, label) {
    if (typeof document.dispatchEvent !== "function" || typeof CustomEvent === "undefined") return;
    document.dispatchEvent(new CustomEvent("aw:anima-activity", {
      detail: {
        anima: this.animaName,
        phase,
        label,
        emotion: this.expression,
        threadId: this.threadId,
      },
    }));
  }

  _onKeyDown(event) {
    if (event.key !== "Escape" || this.finished) return;
    event.preventDefault();
    this.minimize();
  }

  finish() {
    if (this.finished) return Promise.resolve(null);
    this.finished = true;
    const durationSeconds = this.connectedAt === null
      ? 0
      : Math.max(0, Math.floor((this.now() - this.connectedAt) / 1000));
    const transcript = this.transcript.map((line) => ({ ...line }));
    const record = {
      started_at: this.startedAt,
      duration_seconds: durationSeconds,
      thread_id: this.threadId,
      summary: this.lastResponse.slice(0, 60),
      transcript,
    };

    this._emitActivity("call-end", t("chat.call.activity_end"));
    this.listeners.forEach(([event, handler]) => this.voice.off(event, handler));
    this.listeners = [];
    this.clearInterval(this.clockTimer);
    this._clearThinkingTimer();
    document.removeEventListener("keydown", this._onKeyDown);
    this.voice.disconnect();
    this.animators.forEach((animator) => animator.destroy?.());
    this.els.root.remove();
    this.els.pip.remove();
    this.els.transcriptDialog.remove();
    if (_activeCall === this) _activeCall = null;
    this.onClose?.();

    return Promise.resolve()
      .then(() => this.postCall(this.animaName, record))
      .catch((error) => {
        console.warn("[CallScreen] Could not save call record", error);
      })
      .then(() => {
        this.onRecord?.(record);
        return record;
      });
  }
}
