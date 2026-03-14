/**
 * replay-ui.js — Replay control bar for the AnimaWorks Dashboard.
 *
 * Renders a seek bar and playback controls below the KPI bar in the org dashboard.
 * Layout: [◀◀] [▶/⏸] [▶▶] ──●──────────── 09:00 ─ 22:00  [速度: 50x]
 */

import { createLogger } from "../../shared/logger.js";

const logger = createLogger("replay-ui");

// ── Constants ─────────────────────────────────────────────────────────────

const SPEED_CYCLE = [1, 5, 10, 50, 100];
const SKIP_MS = 5 * 60 * 1000; // 5 minutes

// ── Helpers ───────────────────────────────────────────────────────────────

/**
 * Format millisecond timestamp to HH:MM in JST (Asia/Tokyo).
 * @param {number} ms - Unix timestamp in milliseconds
 * @returns {string} Formatted time string
 */
function formatTimeJST(ms) {
  const d = new Date(ms);
  return d.toLocaleTimeString("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Tokyo",
  });
}

// ── ReplayUI ───────────────────────────────────────────────────────────────

/**
 * Replay control bar for the org dashboard.
 * Inserts controls after the KPI bar within the org-canvas-root container.
 */
export class ReplayUI {
  /**
   * @param {object} opts
   * @param {HTMLElement} opts.container - DOM element (org-canvas-root) to insert controls into
   * @param {() => void} opts.onPlay - Called when play is requested
   * @param {() => void} opts.onPause - Called when pause is requested
   * @param {(timeMs: number) => void} opts.onSeek - Called when seek position changes
   * @param {(speed: number) => void} opts.onSpeedChange - Called when speed changes
   * @param {() => void} opts.onExit - Called when exiting replay mode
   */
  constructor({ container, onPlay, onPause, onSeek, onSpeedChange, onExit }) {
    this._container = container;
    this._onPlay = onPlay || (() => {});
    this._onPause = onPause || (() => {});
    this._onSeek = onSeek || (() => {});
    this._onSpeedChange = onSpeedChange || (() => {});
    this._onExit = onExit || (() => {});

    this._startMs = 0;
    this._endMs = 1000;
    this._currentMs = 0;
    this._isPlaying = false;
    this._speedIndex = 0;
    this._isLoading = false;
    this._isDragging = false;

    this._root = null;
    this._playBtn = null;
    this._slider = null;
    this._timeStart = null;
    this._timeCurrent = null;
    this._timeEnd = null;
    this._speedBtn = null;

    this._build();
  }

  _build() {
    this._root = document.createElement("div");
    this._root.className = "org-replay-bar";
    this._root.id = "orgReplayBar";

    this._root.innerHTML = `
      <div class="org-replay-controls">
        <button class="org-replay-btn" id="replayExitBtn" title="Live mode">✕</button>
        <button class="org-replay-btn" id="replayPrevBtn" title="Back 5min">◀◀</button>
        <button class="org-replay-btn org-replay-btn--play" id="replayPlayBtn" title="Play">▶</button>
        <button class="org-replay-btn" id="replayNextBtn" title="Forward 5min">▶▶</button>
      </div>
      <div class="org-replay-seek">
        <span class="org-replay-time" id="replayTimeStart">--:--</span>
        <input type="range" class="org-replay-slider" id="replaySlider" min="0" max="1000" value="0" step="1">
        <span class="org-replay-time" id="replayTimeCurrent">--:--</span>
        <span class="org-replay-time" id="replayTimeEnd">--:--</span>
      </div>
      <button class="org-replay-speed" id="replaySpeedBtn">1x</button>
    `;

    this._playBtn = this._root.querySelector("#replayPlayBtn");
    this._slider = this._root.querySelector("#replaySlider");
    this._timeStart = this._root.querySelector("#replayTimeStart");
    this._timeCurrent = this._root.querySelector("#replayTimeCurrent");
    this._timeEnd = this._root.querySelector("#replayTimeEnd");
    this._speedBtn = this._root.querySelector("#replaySpeedBtn");

    const exitBtn = this._root.querySelector("#replayExitBtn");
    const prevBtn = this._root.querySelector("#replayPrevBtn");
    const nextBtn = this._root.querySelector("#replayNextBtn");

    // Play / Pause toggle
    this._playBtn.addEventListener("click", () => {
      if (this._isPlaying) {
        this._onPause();
      } else {
        this._onPlay();
      }
    });

    // Exit replay
    exitBtn.addEventListener("click", () => this._onExit());

    // Skip back 5 min
    prevBtn.addEventListener("click", () => {
      const target = Math.max(this._startMs, this._currentMs - SKIP_MS);
      this._onSeek(target);
    });

    // Skip forward 5 min
    nextBtn.addEventListener("click", () => {
      const target = Math.min(this._endMs, this._currentMs + SKIP_MS);
      this._onSeek(target);
    });

    // Slider: oninput for live seeking, onchange for final
    this._slider.addEventListener("input", () => {
      this._isDragging = true;
      const time = this._sliderToTime(Number(this._slider.value));
      this._timeCurrent.textContent = formatTimeJST(time);
      this._onSeek(time);
    });
    this._slider.addEventListener("change", () => {
      this._isDragging = false;
      const time = this._sliderToTime(Number(this._slider.value));
      this._onSeek(time);
    });

    // Speed cycle: 1x → 5x → 10x → 50x → 100x → 1x
    this._speedBtn.addEventListener("click", () => {
      this._speedIndex = (this._speedIndex + 1) % SPEED_CYCLE.length;
      const speed = SPEED_CYCLE[this._speedIndex];
      this._speedBtn.textContent = `${speed}x`;
      this._onSpeedChange(speed);
    });

    // Insert after KPI bar
    const kpiBar = this._container?.querySelector("#orgKpiBar");
    if (kpiBar) {
      kpiBar.after(this._root);
    } else {
      this._container?.prepend(this._root);
    }

    this._root.style.display = "none";
    logger.debug("ReplayUI built");
  }

  _sliderToTime(val) {
    const range = this._endMs - this._startMs;
    if (range <= 0) return this._startMs;
    return this._startMs + (val / 1000) * range;
  }

  _timeToSlider(ms) {
    const range = this._endMs - this._startMs;
    if (range <= 0) return 0;
    return ((ms - this._startMs) / range) * 1000;
  }

  /**
   * Show the replay control bar.
   */
  show() {
    if (this._root) this._root.style.display = "";
  }

  /**
   * Hide the replay control bar.
   */
  hide() {
    if (this._root) this._root.style.display = "none";
  }

  /**
   * Update slider position and current time display.
   * @param {number} currentMs - Current playback time in milliseconds
   * @param {number} [progress] - Optional 0–1 progress (used if time range not yet set)
   */
  updateTime(currentMs, progress) {
    this._currentMs = currentMs;
    this._timeCurrent.textContent = formatTimeJST(currentMs);

    if (!this._isDragging) {
      const range = this._endMs - this._startMs;
      const val = range > 0 ? this._timeToSlider(currentMs) : (progress ?? 0) * 1000;
      this._slider.value = String(Math.round(Math.max(0, Math.min(1000, val))));
    }
  }

  /**
   * Set the time range for the slider and display.
   * @param {number} startMs - Range start (milliseconds)
   * @param {number} endMs - Range end (milliseconds)
   */
  updateTimeRange(startMs, endMs) {
    this._startMs = startMs;
    this._endMs = endMs;
    this._timeStart.textContent = formatTimeJST(startMs);
    this._timeEnd.textContent = formatTimeJST(endMs);
    this._slider.min = "0";
    this._slider.max = "1000";
    this._slider.step = "1";
    this.updateTime(this._currentMs);
  }

  /**
   * Update play/pause button state.
   * @param {boolean} isPlaying - Whether playback is active
   */
  setPlaying(isPlaying) {
    this._isPlaying = isPlaying;
    this._playBtn.textContent = isPlaying ? "⏸" : "▶";
    this._playBtn.title = isPlaying ? "Pause" : "Play";
  }

  /**
   * Update speed display.
   * @param {number} speed - Current speed multiplier (1, 5, 10, 50, 100)
   */
  setSpeed(speed) {
    const idx = SPEED_CYCLE.indexOf(speed);
    this._speedIndex = idx >= 0 ? idx : 0;
    this._speedBtn.textContent = `${speed}x`;
  }

  /**
   * Show or hide loading indicator.
   * @param {boolean} isLoading - Whether loading state is active
   */
  setLoading(isLoading) {
    this._isLoading = isLoading;
    this._root?.classList.toggle("org-replay-bar--loading", isLoading);
  }

  /**
   * Remove DOM elements and clean up.
   */
  dispose() {
    this._root?.remove();
    this._root = null;
    this._playBtn = null;
    this._slider = null;
    this._timeStart = null;
    this._timeCurrent = null;
    this._timeEnd = null;
    this._speedBtn = null;
    this._container = null;
    logger.debug("ReplayUI disposed");
  }
}
