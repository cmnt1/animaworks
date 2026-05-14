/**
 * replay-engine.js — Replay engine for AnimaWorks Dashboard (Business 2D org-dashboard).
 *
 * Manages virtual time progression, event queuing, speed control, frame batch processing,
 * and seek/state reconstruction.
 */

import { createLogger } from "../../shared/logger.js";
import { basePath } from "/shared/base-path.js";
import { eventTimeMs, normalizeActivityEvent } from "./activity-normalize.js";

const logger = createLogger("replay-engine");

// ── Constants ───────────────────────────────────────────────────────────────

const MAX_STREAM_ENTRIES = 4;
const SPEED_OPTIONS = [1, 5, 10, 50, 100, 200];
const ONE_HOUR_MS = 60 * 60 * 1000;
const MAX_LIVE_BUFFER = 1000;
const REPLAY_PAGE_LIMIT = 5000;
const MAX_REPLAY_EVENTS = 200000;

/**
 * Get anima name(s) for an event. Returns array of anima names.
 * @param {object} evt
 * @returns {string[]}
 */
function eventAnimas(evt) {
  const semanticNames = semanticEventCardNames(evt);
  if (semanticNames) return semanticNames;
  if (evt.anima) return [evt.anima];
  if (Array.isArray(evt.animas) && evt.animas.length) return evt.animas;
  return [];
}

// ── Card stream entry builder ───────────────────────────────────────────────

function cleanEndpointName(value) {
  return String(value || "").trim().replace(/^#/, "");
}

function semanticEventCardNames(evt) {
  if (!evt?.kind) return null;
  const out = [];
  const actor = cleanEndpointName(evt.actor);
  const target = cleanEndpointName(evt.target);
  if (actor) out.push(actor);
  if (target && !String(evt.target || "").trim().startsWith("#") && target !== actor) {
    out.push(target);
  }
  return out;
}

function isVisibleReplayEvent(evt) {
  if (!evt?.kind) return true;
  return Number(evt.importance || 0) >= 2;
}

function semanticStreamType(evt, cardName) {
  const kind = String(evt.kind || "").toLowerCase();
  const actor = cleanEndpointName(evt.actor);
  const target = cleanEndpointName(evt.target);
  if (kind === "message" || kind === "response") {
    return target && target === cardName && actor !== cardName ? "msg_in" : "msg_out";
  }
  if (kind === "delegation" || kind === "task") return "task";
  if (kind === "channel" || kind === "external") return "board";
  if (kind === "heartbeat") return "heartbeat";
  if (kind === "cron") return "cron";
  if (kind === "memory") return "memory";
  if (kind === "error") return "error";
  return "tool";
}

function summarizeSemanticEvent(evt) {
  const label = String(evt.label || evt.kind || "activity").trim();
  const summary = String(evt.summary || "").trim();
  return (summary ? `${label}: ${summary}` : label).slice(0, 80);
}

function semanticEventToStreamEntry(evt, cardName) {
  return {
    id: evt.id || String(Date.now() + Math.random()),
    type: semanticStreamType(evt, cardName),
    text: summarizeSemanticEvent(evt),
    status: evt.status === "failed" ? "error" : "done",
    ts: eventTimeMs(evt) || Date.now(),
  };
}

function mapEventType(type) {
  if (!type) return "tool";
  const t = String(type).toLowerCase();
  if (t.includes("heartbeat")) return "heartbeat";
  if (t.includes("cron")) return "cron";
  if (t.includes("channel") || t.includes("board")) return "board";
  if (t.includes("tool")) return "tool";
  return "tool";
}

function summarizeEvent(ev) {
  if (ev.summary) return ev.summary.slice(0, 80);
  const type = ev.type || ev.name || "";
  if (type.includes("tool_use")) return ev.tool || ev.tool_name || type;
  if (type.includes("heartbeat")) return "heartbeat";
  if (type.includes("cron")) return ev.task || "cron";
  if (type.includes("message")) return ev.intent ? `${type} (${ev.intent})` : type;
  return type.slice(0, 60) || "activity";
}

function eventToStreamEntry(evt, cardName = "") {
  if (evt.kind) return semanticEventToStreamEntry(evt, cardName);
  return {
    id: evt.id || String(Date.now() + Math.random()),
    type: mapEventType(evt.type || evt.name),
    text: summarizeEvent(evt),
    status: "done",
    ts: eventTimeMs(evt) || Date.now(),
  };
}

// ── Status heuristic for seek ───────────────────────────────────────────────

function statusFromEventType(type) {
  if (!type) return "idle";
  const t = String(type).toLowerCase();
  if (t === "heartbeat_start") return "working";
  if (t === "heartbeat_end" || t === "cron_executed" || t === "response_sent" || t === "message_sent") return "idle";
  return "idle";
}

function statusFromEvent(evt) {
  if (evt?.kind) {
    return evt.status === "started" || evt.status === "progress" ? "working" : "idle";
  }
  return statusFromEventType(evt?.type || evt?.name);
}

// ── ReplayEngine ─────────────────────────────────────────────────────────────

/**
 * Replay engine for org-dashboard: virtual time, event playback, seek, WS buffer.
 */
export class ReplayEngine {
  /**
   * @param {object} options
   * @param {function(object, number): void} options.onEvent — (event, speed) per event
   * @param {function(object): void} options.onSeekRebuild — ({ cardStreams, cardStatus, kpiCounts }) after seek
   * @param {function(): void} options.onComplete — when replay reaches end
   * @param {function(number, number): void} options.onTimeUpdate — (currentTimeMs, progress) per frame
   */
  constructor({ onEvent, onSeekRebuild, onComplete, onTimeUpdate } = {}) {
    this._onEvent = onEvent || (() => {});
    this._onSeekRebuild = onSeekRebuild || (() => {});
    this._onComplete = onComplete || (() => {});
    this._onTimeUpdate = onTimeUpdate || (() => {});

    this._events = [];
    this._timeRange = { start: 0, end: 0 };
    this._cursor = 0;
    this._virtualTimeMs = 0;
    this._speed = 1;
    this._playing = false;
    this._loaded = false;
    this._rafId = null;
    this._lastWallMs = 0;
    this._liveBuffer = [];
    this._lastTimeUpdateWall = 0;
  }

  /**
   * Fetch events from API and set time range.
   * @param {number} [hours=12]
   * @returns {Promise<void>}
   */
  async load(hours = 12) {
    try {
      const raw = [];
      let offset = 0;

      while (true) {
        const params = new URLSearchParams({
          hours: String(hours),
          limit: String(REPLAY_PAGE_LIMIT),
          offset: String(offset),
          replay: "true",
          grouped: "true",
          semantic: "true",
        });
        const res = await fetch(`${basePath}/api/activity/recent?${params.toString()}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data = await res.json();
        const pageEvents = data.events || [];
        const total = Number(data.raw_total || data.total || 0);
        if (total > MAX_REPLAY_EVENTS || raw.length + pageEvents.length > MAX_REPLAY_EVENTS) {
          throw new Error(`Replay range too large (${total || raw.length + pageEvents.length} events). Choose a shorter range.`);
        }
        if (data.has_more && pageEvents.length === 0) {
          throw new Error("Replay page stalled while has_more=true");
        }

        raw.push(...pageEvents);
        if (!data.has_more) break;
        offset += pageEvents.length;
      }

      this._events = raw.map(normalizeActivityEvent).filter((e) => eventTimeMs(e) > 0);
      this._events.sort((a, b) => eventTimeMs(a) - eventTimeMs(b));

      const now = Date.now();
      const rangeStart = now - hours * ONE_HOUR_MS;
      if (this._events.length === 0) {
        this._timeRange = { start: rangeStart, end: now };
      } else {
        this._timeRange = {
          start: Math.min(rangeStart, eventTimeMs(this._events[0])),
          end: Math.max(now, eventTimeMs(this._events[this._events.length - 1])),
        };
      }

      this._cursor = 0;
      this._virtualTimeMs = this._timeRange.start;
      this._loaded = true;
      logger.info("Replay loaded", { events: this._events.length, hours, range: this._timeRange });
    } catch (err) {
      logger.error("Replay load failed", err);
      this._events = [];
      this._timeRange = { start: 0, end: 0 };
      this._loaded = false;
      throw err;
    }
  }

  /**
   * Start or resume playback.
   */
  play() {
    if (!this._loaded) return;
    this._playing = true;
    this._lastWallMs = performance.now();
    this._tick();
  }

  /**
   * Pause playback.
   */
  pause() {
    this._playing = false;
    if (this._rafId) {
      cancelAnimationFrame(this._rafId);
      this._rafId = null;
    }
  }

  /**
   * Jump to absolute time (ms since epoch). Rebuilds state by scanning events.
   * @param {number} timeMs
   */
  seek(timeMs) {
    if (!this._loaded) return;
    const { start, end } = this._timeRange;
    this._virtualTimeMs = Math.max(start, Math.min(end, timeMs));
    this._cursor = 0;

    const cardStreams = new Map();
    const cardStatus = new Map();
    let eventsInLastHour = 0;
    const hourBeforeT = this._virtualTimeMs - ONE_HOUR_MS;

    for (let i = 0; i < this._events.length; i++) {
      const evt = this._events[i];
      const ts = eventTimeMs(evt);
      if (ts > this._virtualTimeMs) break;
      if (!isVisibleReplayEvent(evt)) continue;

      const animas = eventAnimas(evt);
      const status = statusFromEvent(evt);
      for (const name of animas) {
        if (!name) continue;
        let entries = cardStreams.get(name) || [];
        entries.push(eventToStreamEntry(evt, name));
        if (entries.length > MAX_STREAM_ENTRIES) entries = entries.slice(-MAX_STREAM_ENTRIES);
        cardStreams.set(name, entries);
        cardStatus.set(name, status);
      }

      if (ts >= hourBeforeT) eventsInLastHour++;
    }

    this._cursor = this._events.findIndex((e) => eventTimeMs(e) > this._virtualTimeMs);
    if (this._cursor < 0) this._cursor = this._events.length;

    this._onSeekRebuild({
      cardStreams,
      cardStatus,
      kpiCounts: { eventsInLastHour, activeTasks: 0 },
    });
    this._onTimeUpdate(this._virtualTimeMs, this.getProgress());
  }

  /**
   * Set playback speed (1, 5, 10, 50, 100, 200).
   * @param {number} speed
   */
  setSpeed(speed) {
    const v = Number(speed);
    if (SPEED_OPTIONS.includes(v)) this._speed = v;
    else this._speed = Math.max(1, Math.min(200, Math.round(v)));
  }

  /** @returns {number} */
  getSpeed() {
    return this._speed;
  }

  /** @returns {boolean} */
  isPlaying() {
    return this._playing;
  }

  /** @returns {boolean} */
  isLoaded() {
    return this._loaded;
  }

  /**
   * @returns {{ start: number, end: number }} Time range in ms
   */
  getTimeRange() {
    return { ...this._timeRange };
  }

  /** @returns {number} Current virtual time in ms */
  getCurrentTime() {
    return this._virtualTimeMs;
  }

  /**
   * @returns {number} Progress 0..1
   */
  getProgress() {
    const { start, end } = this._timeRange;
    if (end <= start) return 1;
    return Math.max(0, Math.min(1, (this._virtualTimeMs - start) / (end - start)));
  }

  /**
   * Cancel RAF and clean up.
   */
  dispose() {
    this.pause();
    this._loaded = false;
    this._events = [];
    this._liveBuffer = [];
  }

  /**
   * Store event from WebSocket during replay for later application.
   * @param {object} event
   */
  bufferLiveEvent(event) {
    if (this._liveBuffer.length < MAX_LIVE_BUFFER) {
      this._liveBuffer.push(event);
    }
  }

  /**
   * Return buffered live events and clear buffer.
   * @returns {object[]}
   */
  flushLiveBuffer() {
    const out = [...this._liveBuffer];
    this._liveBuffer = [];
    return out;
  }

  // ── Internal ───────────────────────────────────────────────────────────────

  _tick() {
    if (!this._playing) return;

    const now = performance.now();
    const wallDelta = (now - this._lastWallMs) / 1000;
    this._lastWallMs = now;

    const virtualDelta = wallDelta * this._speed * 1000;
    const nextVirtual = Math.min(this._timeRange.end, this._virtualTimeMs + virtualDelta);

    while (this._cursor < this._events.length) {
      const evt = this._events[this._cursor];
      const ts = eventTimeMs(evt);
      if (ts > nextVirtual) break;
      if (isVisibleReplayEvent(evt)) this._onEvent(evt, this._speed);
      this._cursor++;
    }

    this._virtualTimeMs = nextVirtual;
    if (now - this._lastTimeUpdateWall >= 66) {
      this._lastTimeUpdateWall = now;
      this._onTimeUpdate(this._virtualTimeMs, this.getProgress());
    }

    if (this._virtualTimeMs >= this._timeRange.end) {
      this._playing = false;
      if (this._rafId) {
        cancelAnimationFrame(this._rafId);
        this._rafId = null;
      }
      this._onComplete();
      return;
    }

    this._rafId = requestAnimationFrame(() => this._tick());
  }
}
