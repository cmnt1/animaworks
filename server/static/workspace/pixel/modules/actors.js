import { SpriteSheet } from "./sprite.js";
import { drawPixelText, measurePixelText } from "./pixel-text.js";

const STATE_MAP = Object.freeze({
  idle: { animation: "idle", bubble: "bubble_break" },
  working: { animation: "working", bubble: "bubble_working" },
  working_scheduled: { animation: "working", bubble: "bubble_cron" },
  thinking: { animation: "thinking", bubble: "bubble_thinking" },
  talking: { animation: "talking", bubble: "bubble_meeting" },
  reporting: { animation: "talking", bubble: "bubble_reporting" },
  sleeping: { animation: "sleeping", bubble: "bubble_sleeping" },
  success: { animation: "success", bubble: "" },
  error: { animation: "error", bubble: "bubble_error" },
  walking: { animation: "walk_down", bubble: "" },
});

const COMPACT_STATUS_COLORS = Object.freeze({
  idle: "#c98d9c",
  working: "#72b98e",
  success: "#e7bd5f",
  walking: "#6fa4bc",
  sleeping: "#8f8ab8",
});

// Seconds without any runtime event before the displayed state decays toward
// sleeping. Scheduled work keeps a longer grace because LLM turns can be
// silent between tool calls.
const STATE_DECAY_SECONDS = Object.freeze({
  working_scheduled: 300,
  working: 300,
  thinking: 600,
  idle: 180,
  success: 90,
});

// Short "何をしているか" labels derived from the tool an anima just used.
const TOOL_ACTIVITY_LABELS = [
  [/^(bash|read|glob|grep|edit|write|apply_patch|machine)$/, "コーディング中"],
  [/send_message|broadcast|post_channel/, "メッセージ対応中"],
  [/call_human/, "報告準備中"],
  [/delegate_task/, "委任手配中"],
  [/search_memory|read_memory/, "調べ物中"],
  [/write_memory|archive_memory/, "記録整理中"],
  [/report_knowledge|report_procedure|completion_gate/, "知識整理中"],
  [/list_tasks|update_task|^goal$/, "タスク管理中"],
  [/skill/, "スキル整備中"],
  [/web_search|web_fetch|browser|fetch_url/, "調査中"],
];

function labelForTool(tool) {
  const name = String(tool || "").toLowerCase();
  if (!name) return "";
  for (const [pattern, label] of TOOL_ACTIVITY_LABELS) {
    if (pattern.test(name)) return label;
  }
  return "";
}

const DYNAMIC_BUBBLE_TEXT = Object.freeze({
  fontSize: 9,
  scale: 1,
  bold: true,
  bitmap: false,
});

const NAME_TEXT_OPTIONS = Object.freeze({
  fontSize: 4,
  scale: 1,
  bold: true,
  letterSpacing: 3,
});

function normalizeState(value) {
  const raw = typeof value === "object" ? value?.state || value?.status : value;
  const state = String(raw || "idle").toLowerCase();
  if (STATE_MAP[state]) return state;
  if (state === "not_found" || state === "stopped") return "sleeping";
  // A running process with no observed activity is just waiting for work.
  if (state === "running" || state === "starting") return "sleeping";
  if (state.startsWith("cron") || state.startsWith("heartbeat") || state.startsWith("task")) {
    return "working_scheduled";
  }
  if (state.includes("bootstrap") || state.includes("think") || state.includes("process")) return "thinking";
  if (state.includes("work") || state.includes("busy")) return "working";
  if (state.includes("error") || state.includes("fail")) return "error";
  if (state.includes("sleep") || state.includes("stop") || state.includes("inactive")) return "sleeping";
  if (state.includes("talk") || state.includes("chat")) return "talking";
  if (state.includes("report")) return "reporting";
  if (state.includes("success") || state.includes("complete")) return "success";
  return "idle";
}

function tileKey(x, y) {
  return `${x},${y}`;
}

// Initial state for an actor at page load. The busy sidecar from /api/animas
// reports in-progress work, so active animas start awake instead of waiting
// for the next live event.
function initialActorState(anima) {
  const busy = anima?.busy;
  if (busy?.is_busy) {
    const progressAt = Date.parse(busy.last_progress_at || busy.busy_since || "");
    const fresh = Number.isFinite(progressAt) && Date.now() - progressAt < 15 * 60 * 1000;
    if (fresh) {
      const lanes = (busy.lanes || []).join(",");
      return lanes.includes("chat") ? "thinking" : "working_scheduled";
    }
  }
  return anima?.status || "idle";
}

function buildBlocked(scene) {
  const blocked = new Set();
  for (const desk of Object.values(scene.desks)) {
    const [x, y] = desk.tile;
    const half = desk.wide ? 2 : 1;
    for (let dx = -half; dx <= half; dx += 1) {
      blocked.add(tileKey(x + dx, y));
      blocked.add(tileKey(x + dx, y + 1));
    }
  }
  for (const [name, prop] of Object.entries(scene.props)) {
    if (name === "plants" || name === "welcome_mat" || name === "cat" || prop.under) continue;
    for (let dx = 0; dx < prop.w; dx += 1) {
      for (let dy = 0; dy < prop.h; dy += 1) {
        blocked.add(tileKey(prop.tile[0] + dx, prop.tile[1] + dy));
      }
    }
  }
  for (const [x, y] of scene.props.plants || []) blocked.add(tileKey(x, y));
  return blocked;
}

function buildBackgroundBlocked(scene) {
  const blocked = new Set();
  const slots = [
    ...(scene.background_mode?.slots?.slots || []),
    scene.background_mode?.slots?.human,
  ].filter(Boolean);
  for (const slot of slots) {
    const deskRect = slot.desk_rect || [slot.x - 56, slot.y + 8, 112, 72];
    const left = Math.floor(deskRect[0] / scene.canvas.tile);
    const right = Math.floor((deskRect[0] + deskRect[2] - 1) / scene.canvas.tile);
    const top = Math.floor(deskRect[1] / scene.canvas.tile);
    const bottom = Math.floor((deskRect[1] + deskRect[3] - 1) / scene.canvas.tile);
    for (let x = left; x <= right; x += 1) {
      for (let y = top; y <= bottom; y += 1) blocked.add(tileKey(x, y));
    }
  }
  return blocked;
}

function waypointCandidates(scene) {
  const points = [];
  for (const prop of Object.values(scene.props || {})) {
    const sprite = prop.sprite || "";
    if (prop.kind === "meeting") {
      points.push(
        [prop.tile[0] - 1, prop.tile[1]],
        [prop.tile[0] + prop.w, prop.tile[1]],
        [prop.tile[0], prop.tile[1] + prop.h],
        [prop.tile[0] + prop.w - 1, prop.tile[1] + prop.h],
      );
    } else if (sprite === "sofa" || sprite === "coffee") {
      const frontY = prop.tile[1] + prop.h + (sprite === "coffee" ? 1 : 0);
      points.push([prop.tile[0] + Math.floor(prop.w / 2), frontY]);
    }
  }
  const width = scene.canvas.w / scene.canvas.tile;
  const height = scene.canvas.h / scene.canvas.tile;
  return points.filter(([x, y]) => x >= 1 && x < width - 1 && y >= 4 && y < height - 1);
}

function findPath(start, goal, blocked, scene) {
  const width = scene.canvas.w / scene.canvas.tile;
  const height = scene.canvas.h / scene.canvas.tile;
  const minimumY = scene.background_mode?.enabled ? 6 : 4;
  const startKey = tileKey(...start);
  const goalKey = tileKey(...goal);
  const open = [{ point: start, f: 0 }];
  const cameFrom = new Map();
  const gScore = new Map([[startKey, 0]]);
  const seen = new Set();
  const heuristic = ([x, y]) => Math.abs(x - goal[0]) + Math.abs(y - goal[1]);

  while (open.length) {
    open.sort((a, b) => a.f - b.f);
    const current = open.shift().point;
    const currentKey = tileKey(...current);
    if (currentKey === goalKey) {
      const path = [current];
      let cursor = currentKey;
      while (cameFrom.has(cursor)) {
        const previous = cameFrom.get(cursor);
        path.push(previous);
        cursor = tileKey(...previous);
      }
      return path.reverse();
    }
    if (seen.has(currentKey)) continue;
    seen.add(currentKey);
    const neighbors = [
      [current[0] + 1, current[1]], [current[0] - 1, current[1]],
      [current[0], current[1] + 1], [current[0], current[1] - 1],
    ];
    for (const next of neighbors) {
      const [x, y] = next;
      if (x < 1 || x >= width - 1 || y < minimumY || y >= height - 1) continue;
      const key = tileKey(x, y);
      if (key !== goalKey && blocked.has(key)) continue;
      const score = (gScore.get(currentKey) ?? Infinity) + 1;
      if (score >= (gScore.get(key) ?? Infinity)) continue;
      cameFrom.set(key, current);
      gScore.set(key, score);
      open.push({ point: next, f: score + heuristic(next) });
    }
  }
  return [start, goal];
}

export class Actor {
  constructor(id, definition, homeTile, tileSize, seatPosition, assets, metadata = {}) {
    this.id = id;
    this.company = metadata.company || "default";
    this.isHuman = Boolean(metadata.isHuman);
    this.homeTile = [...homeTile];
    this.tileSize = tileSize;
    this.seatPosition = { ...seatPosition };
    this.x = seatPosition.x;
    this.y = seatPosition.y;
    this.sprite = new SpriteSheet(definition);
    this.assets = assets;
    this.backgroundSlot = metadata.backgroundSlot || null;
    // The 96px seated rows retain 12px of lower-body composition below the
    // logical feet anchor. Keep the logical baseline at the desk's back edge,
    // then compensate only while rendering the seated pose.
    this.seatedRenderOffsetY = metadata.seatedRenderOffsetY || 0;
    const deskRect = this.backgroundSlot?.desk_rect;
    const frontRect = this.backgroundSlot?.occlusion_rect;
    this.backgroundNamePosition = this.backgroundSlot ? {
      x: deskRect ? deskRect[0] + deskRect[2] / 2 : this.backgroundSlot.x,
      y: deskRect && deskRect[1] < 300 && frontRect
        ? frontRect[1] + 4
        : deskRect
          ? deskRect[1] + deskRect[3] - 15
          : this.backgroundSlot.y + 65,
    } : null;
    this.state = "idle";
    this.bubble = "";
    this.bubbleOverride = "";
    this.bubbleOverrideRemaining = 0;
    this.fxTime = 0;
    this.motion = null;
    this.isSeated = true;
    this.idleSeconds = 0;
    this.activityLabel = "";
    this.activityLabelRemaining = 0;
  }

  setState(value) {
    this.state = normalizeState(value);
    this.idleSeconds = 0;
    if (this.state === "sleeping") this.setActivityLabel("");
    const mapping = STATE_MAP[this.state];
    this.bubble = mapping.bubble;
    if (!this.motion) {
      this.sprite.setAnimation(this.isSeated ? mapping.animation : "walk_down");
    }
  }

  noteActivity() {
    this.idleSeconds = 0;
  }

  setActivityLabel(label, duration = 30) {
    this.activityLabel = label || "";
    this.activityLabelRemaining = this.activityLabel ? duration : 0;
  }

  dynamicLabel() {
    if (!this.activityLabel) return "";
    if (this.state !== "working_scheduled" && this.state !== "working") return "";
    return this.activityLabel;
  }

  renderScale() {
    return this.isSeated ? 1 : 1.5;
  }

  walk(path, speed = 120) {
    const includeHomeStep = this.isSeated;
    const route = includeHomeStep ? path : path.slice(1);
    const points = route.map(([x, y]) => ({
      x: (x + 0.5) * this.tileSize,
      y: (y + 1) * this.tileSize,
    }));
    return this.walkPixels(points, speed);
  }

  walkToSeat(speed = 120) {
    return this.walkPixels([{
      x: this.seatPosition.x,
      y: this.seatPosition.y + this.seatedRenderOffsetY,
    }], speed);
  }

  walkPixels(points, speed = 120) {
    if (this.motion?.resolve) this.motion.resolve(false);
    if (!points.length) return Promise.resolve(true);
    return new Promise((resolve) => {
      if (this.isSeated) this.y = this.visualY();
      this.isSeated = false;
      const first = points[0];
      const dx = first.x - this.x;
      const dy = first.y - this.y;
      this.sprite.setAnimation(
        Math.abs(dx) > Math.abs(dy) ? "walk_side" : (dy < 0 ? "walk_up" : "walk_down"),
        Math.abs(dx) > Math.abs(dy) && dx > 0,
      );
      this.motion = { points, speed, resolve };
      this.bubble = "";
    });
  }

  update(deltaSeconds) {
    this.fxTime += deltaSeconds;
    this.idleSeconds += deltaSeconds;
    const decayLimit = STATE_DECAY_SECONDS[this.state];
    if (decayLimit && !this.isHuman && this.isSeated && !this.motion &&
        this.idleSeconds > decayLimit) {
      this.setState("sleeping");
    }
    if (this.bubbleOverrideRemaining > 0) {
      this.bubbleOverrideRemaining = Math.max(0, this.bubbleOverrideRemaining - deltaSeconds);
      if (this.bubbleOverrideRemaining === 0) this.bubbleOverride = "";
    }
    if (this.activityLabelRemaining > 0) {
      this.activityLabelRemaining = Math.max(0, this.activityLabelRemaining - deltaSeconds);
      if (this.activityLabelRemaining === 0) this.activityLabel = "";
    }
    this.sprite.update(deltaSeconds * (this.state === "working" ? 1.5 : 1));
    if (!this.motion) return;
    let remaining = this.motion.speed * deltaSeconds;
    while (remaining > 0 && this.motion) {
      const target = this.motion.points[0];
      const dx = target.x - this.x;
      const dy = target.y - this.y;
      const distance = Math.hypot(dx, dy);
      if (distance <= remaining) {
        this.x = target.x;
        this.y = target.y;
        remaining -= distance;
        this.motion.points.shift();
        if (!this.motion.points.length) {
          const resolve = this.motion.resolve;
          this.motion = null;
          const mapping = STATE_MAP[this.state];
          this.sprite.setAnimation(this.isSeated ? mapping.animation : "walk_down");
          this.bubble = mapping.bubble;
          resolve(true);
        }
        continue;
      }
      const horizontal = Math.abs(dx) > Math.abs(dy);
      if (horizontal) this.sprite.setAnimation("walk_side", dx > 0);
      else this.sprite.setAnimation(dy < 0 ? "walk_up" : "walk_down");
      this.x += (dx / distance) * remaining;
      this.y += (dy / distance) * remaining;
      remaining = 0;
    }
  }

  sit() {
    this.x = this.seatPosition.x;
    this.y = this.seatPosition.y;
    this.isSeated = true;
    const mapping = STATE_MAP[this.state];
    this.sprite.setAnimation(mapping.animation);
    this.bubble = mapping.bubble;
  }

  setTransientBubble(name, duration = 1.5) {
    this.bubbleOverride = name;
    this.bubbleOverrideRemaining = duration;
  }

  clearTransientBubble() {
    this.bubbleOverride = "";
    this.bubbleOverrideRemaining = 0;
  }

  visualY() {
    return this.y + (this.isSeated ? this.seatedRenderOffsetY : 0);
  }

  spriteY() {
    return this.visualY() - (this.isSeated && this.state === "sleeping" ? 14 : 0);
  }

  draw(ctx) {
    const spriteY = this.spriteY();
    const scale = this.renderScale();
    ctx.save();
    ctx.globalAlpha = 0.18;
    ctx.fillStyle = "#1b1218";
    ctx.beginPath();
    ctx.ellipse(
      Math.round(this.x),
      Math.round(spriteY - 2),
      Math.max(18, Math.round(this.sprite.frameW * scale * (this.isSeated ? 0.22 : 0.27))),
      Math.max(5, Math.round(this.sprite.frameH * scale * 0.065)),
      0,
      0,
      Math.PI * 2,
    );
    ctx.fill();
    ctx.restore();
    this.sprite.draw(ctx, this.x, spriteY, scale);
  }

  drawStatusOverlay(ctx, options = {}) {
    const spriteY = this.spriteY();
    if (this.hasFullBubble()) {
      this.drawBubble(ctx, this.currentBubble(), spriteY, {
        offsetY: options.bubbleOffsetY || 0,
        offsetX: options.bubbleOffsetX || 0,
      });
      return;
    }
    this.drawStateAccent(ctx, spriteY);
  }

  drawNameOverlay(ctx, options = {}) {
    const position = {
      ...(options.namePosition || {}),
      offsetY: options.nameOffsetY || 0,
    };
    this.drawName(ctx, position);
    this.drawStatusDot(ctx, position);
  }

  drawOverlay(ctx, options = {}) {
    this.drawStatusOverlay(ctx, options);
    this.drawNameOverlay(ctx, options);
  }

  currentBubble() {
    if (this.bubbleOverride) return this.bubbleOverride;
    return STATE_MAP[this.state]?.bubble ?? "bubble_break";
  }

  isCompactStatus() {
    if (this.dynamicLabel()) return false;
    return !this.bubbleOverride && Object.hasOwn(COMPACT_STATUS_COLORS, this.state);
  }

  hasFullBubble() {
    return !this.isCompactStatus() && Boolean(this.currentBubble());
  }

  nameBounds(position = {}) {
    const width = Math.max(28, measurePixelText(this.id, NAME_TEXT_OPTIONS) + 6);
    const x = Math.round(position.x ?? this.x);
    const y = Math.round((position.y ?? this.y + 3) + (position.offsetY || 0));
    return {
      x: x - width / 2 - 1,
      y,
      width: width + 12,
      height: 11,
    };
  }

  dynamicBubbleSize() {
    const label = this.dynamicLabel();
    const textWidth = measurePixelText(label, DYNAMIC_BUBBLE_TEXT);
    return { width: textWidth + 22, height: 30 };
  }

  bubbleBounds(name = this.currentBubble(), spriteY = this.spriteY(), offsetY = 0, offsetX = 0) {
    if (this.dynamicLabel()) {
      const size = this.dynamicBubbleSize();
      const x = Math.round(this.x - size.width / 2 + offsetX);
      const headTop = this.headTop(spriteY);
      const headGap = this.backgroundSlot ? 0 : 8;
      const y = Math.round(headTop - headGap - (size.height - 3) + offsetY);
      return { x, y, width: size.width, height: size.height };
    }
    const definition = this.assets.fxDefinition(name, name);
    const width = definition.frameW;
    const height = definition.frameH;
    const x = Math.round(this.x - width / 2 + offsetX);
    const headTop = this.headTop(spriteY);
    const tailBottom = definition.frameH - 3;
    const headGap = this.backgroundSlot ? 0 : 8;
    const bob = this.backgroundSlot ? 0 : Math.sin(this.fxTime * 3) * 2;
    const y = Math.round(
      headTop - headGap - tailBottom + bob + offsetY,
    );
    return { x, y, width, height };
  }

  drawName(ctx, position = {}) {
    ctx.save();
    const width = Math.max(28, measurePixelText(this.id, NAME_TEXT_OPTIONS) + 6);
    const x = Math.round(position.x ?? this.x);
    const y = Math.round((position.y ?? this.y + 3) + (position.offsetY || 0));
    ctx.fillStyle = "#573722";
    ctx.fillRect(x - width / 2 - 1, y, width + 2, 11);
    ctx.fillStyle = "#f3dfb5";
    ctx.fillRect(x - width / 2, y + 1, width, 9);
    drawPixelText(ctx, this.id, x, y + 5, {
      ...NAME_TEXT_OPTIONS,
      align: "center",
      baseline: "middle",
      color: "#493020",
    });
    ctx.restore();
  }

  drawStatusDot(ctx, position = {}) {
    const width = Math.max(28, measurePixelText(this.id, NAME_TEXT_OPTIONS) + 6);
    const x = Math.round(position.x ?? this.x) + Math.ceil(width / 2) + 3;
    const y = Math.round((position.y ?? this.y + 3) + (position.offsetY || 0)) + 1;
    ctx.save();
    ctx.fillStyle = "#573722";
    ctx.fillRect(x, y, 8, 8);
    ctx.fillStyle = this.hasFullBubble()
      ? "#3a2f33"
      : (COMPACT_STATUS_COLORS[this.state] || "#8b7a70");
    ctx.fillRect(x + 1, y + 1, 6, 6);
    ctx.restore();
  }

  drawBubble(ctx, name, spriteY, options = {}) {
    const label = this.dynamicLabel();
    if (label) {
      this.drawDynamicBubble(ctx, label, spriteY, options);
      return;
    }
    const definition = this.assets.fxDefinition(name, name);
    const frame = Math.floor(this.fxTime * definition.fps) % definition.frames;
    const scale = 1;
    const width = Math.round(definition.frameW * scale);
    const height = Math.round(definition.frameH * scale);
    const bounds = this.bubbleBounds(
      name,
      spriteY,
      options.offsetY || 0,
      options.offsetX || 0,
    );
    const x = bounds.x;
    const y = bounds.y;
    ctx.save();
    if (options.quiet) ctx.globalAlpha = 0.55;
    ctx.drawImage(
      definition.image,
      frame * definition.frameW,
      definition.row * definition.frameH,
      definition.frameW,
      definition.frameH,
      x,
      y,
      width,
      height,
    );
    ctx.restore();
  }

  // Hand-drawn speech bubble for dynamic activity labels ("コーディング中"
  // etc.), styled to match the baked fx/bubbles.png rows.
  drawDynamicBubble(ctx, label, spriteY, options = {}) {
    const bounds = this.bubbleBounds("", spriteY, options.offsetY || 0, options.offsetX || 0);
    const { x, y, width } = bounds;
    const bodyHeight = bounds.height - 6;
    const border = "#3f7a38";
    const fill = "#fbf0e4";
    ctx.save();
    if (options.quiet) ctx.globalAlpha = 0.55;
    ctx.fillStyle = border;
    ctx.fillRect(x + 2, y, width - 4, bodyHeight);
    ctx.fillRect(x, y + 2, width, bodyHeight - 4);
    ctx.fillStyle = fill;
    ctx.fillRect(x + 3, y + 2, width - 6, bodyHeight - 4);
    ctx.fillRect(x + 2, y + 3, width - 4, bodyHeight - 6);
    // tail
    const tailX = Math.round(x + width / 2);
    ctx.fillStyle = border;
    ctx.fillRect(tailX - 4, y + bodyHeight, 8, 2);
    ctx.fillRect(tailX - 2, y + bodyHeight + 2, 4, 2);
    ctx.fillStyle = fill;
    ctx.fillRect(tailX - 3, y + bodyHeight - 1, 6, 2);
    drawPixelText(ctx, label, tailX, y + Math.round(bodyHeight / 2), {
      ...DYNAMIC_BUBBLE_TEXT,
      align: "center",
      baseline: "middle",
      color: "#356b2e",
    });
    ctx.restore();
  }

  headTop(spriteY) {
    const headInset = {
      thinking: 5,
      talking: 6,
      reporting: 6,
      sleeping: 28,
      error: 6,
    }[this.state] || 10;
    const scale = this.renderScale();
    return spriteY - (this.sprite.frameH - headInset) * scale;
  }

  drawStateAccent(ctx, spriteY) {
    const headTop = this.headTop(spriteY);
    if (this.state === "error") {
      this.drawFx(ctx, "smoke", this.x - 31, headTop + 24, this.fxTime);
      this.drawFx(ctx, "bubble_small_exclamation", this.x + 37, headTop + 7, this.fxTime);
    } else if (this.state === "thinking") {
      this.drawFx(ctx, "bubble_small_question", this.x + 37, headTop + 7, this.fxTime);
    } else if (this.state === "sleeping") {
      this.drawFx(ctx, "bubble_small_sleep", this.x + 39, headTop + 9, this.fxTime);
    } else if (this.state === "success") {
      this.drawFx(ctx, "sparkle", this.x - 34, headTop + 22, this.fxTime);
      this.drawFx(ctx, "sparkle", this.x + 33, headTop + 5, this.fxTime + 0.22);
    } else if (this.state === "talking") {
      this.drawFx(ctx, "bubble_small_music", this.x + 38, headTop + 9, this.fxTime);
    }
  }

  drawFx(ctx, name, x, y, time) {
    const definition = this.assets.fxDefinition(name, name);
    const frame = Math.floor(time * definition.fps) % definition.frames;
    ctx.drawImage(
      definition.image,
      frame * definition.frameW,
      definition.row * definition.frameH,
      definition.frameW,
      definition.frameH,
      Math.round(x - definition.frameW / 2),
      Math.round(y - definition.frameH / 2),
      definition.frameW,
      definition.frameH,
    );
  }
}

export class ActorManager {
  constructor(scene, assets) {
    this.scene = scene;
    this.assets = assets;
    this.tile = scene.canvas.tile;
    this.blocked = scene.background_mode?.enabled
      ? buildBackgroundBlocked(scene)
      : buildBlocked(scene);
    this.actors = new Map();
    this.destinationReservations = new Map();
    this.actorReservations = new Map();
    const standingWaypoints = scene.background_mode?.slots?.standing_waypoints;
    this.waypoints = scene.background_mode?.enabled
      ? [
        ...(standingWaypoints?.meeting || [[14, 8], [16, 8], [18, 8], [20, 8]]),
        ...(standingWaypoints?.lounge || [[8, 15], [10, 15], [24, 15], [26, 15]]),
      ]
      : waypointCandidates(scene);
  }

  initialize(animas = []) {
    const known = new Map(animas.map((anima) => [
      String(anima.name || anima.id).toLowerCase(),
      anima,
    ]));
    const backgroundSlots = this.scene.background_mode?.slots;
    const availableSlots = backgroundSlots?.slots || [];
    let slotIndex = 0;
    const deskEntries = Object.entries(this.scene.desks || {});
    const orderedEntries = backgroundSlots
      ? deskEntries.sort(([leftId, leftDesk], [rightId, rightDesk]) => {
        const leftHuman = leftDesk.is_human || leftId === (this.scene.human_id || "human");
        const rightHuman = rightDesk.is_human || rightId === (this.scene.human_id || "human");
        if (leftHuman !== rightHuman) return leftHuman ? 1 : -1;
        const companyOrder = String(leftDesk.company || known.get(leftId)?.company || "")
          .localeCompare(String(rightDesk.company || known.get(rightId)?.company || ""), "en", {
            sensitivity: "base",
            numeric: true,
          });
        return companyOrder || leftId.localeCompare(rightId, "en", {
          sensitivity: "base",
          numeric: true,
        });
      })
      : deskEntries;
    for (const [id, desk] of orderedEntries) {
      const isHuman = desk.is_human || id === (this.scene.human_id || "human");
      const backgroundSlot = backgroundSlots
        ? (isHuman ? backgroundSlots.human : availableSlots[slotIndex++])
        : null;
      let home;
      let seatPosition;
      if (backgroundSlot) {
        const deskTop = backgroundSlot.desk_rect?.[1] ?? backgroundSlot.y + 8;
        seatPosition = { x: backgroundSlot.x, y: deskTop + 6 };
        home = [
          Math.round(backgroundSlot.x / this.tile - 0.5),
          Math.round((backgroundSlot.y + 100) / this.tile - 1),
        ];
      } else {
        home = [desk.tile[0], desk.tile[1] + 2];
        const deskFootY = (desk.tile[1] + 2) * this.tile;
        const deskAsset = this.assets.prop(isHuman ? "desk_taka" : "desk");
        const deskHeight = deskAsset.naturalHeight || deskAsset.height || (isHuman ? 80 : 72);
        seatPosition = {
          x: desk.tile[0] * this.tile + this.tile / 2 + (desk.seat_offset_x ?? 12),
          y: deskFootY - (desk.seat_sink ?? Math.round(deskHeight * 0.4)),
        };
      }
      const actor = new Actor(
        id,
        this.assets.character(isHuman ? "human" : id),
        home,
        this.tile,
        seatPosition,
        this.assets,
        {
          company: desk.company || known.get(id)?.company || "default",
          isHuman,
          backgroundSlot,
          seatedRenderOffsetY: backgroundSlot?.seated_render_offset_y ??
            backgroundSlots?.seated_render_offset_y ?? 12,
        },
      );
      actor.setState(isHuman ? "idle" : initialActorState(known.get(id)));
      this.actors.set(id, actor);
    }
  }

  values() {
    return this.actors.values();
  }

  get(id) {
    return this.actors.get(String(id || "").toLowerCase());
  }

  ids(options = {}) {
    return [...this.actors.values()]
      .filter((actor) => options.includeHuman !== false || !actor.isHuman)
      .map((actor) => actor.id);
  }

  companyOf(id) {
    return this.get(id)?.company || null;
  }

  isHuman(id) {
    return Boolean(this.get(id)?.isHuman);
  }

  setState(id, state) {
    this.get(id)?.setState(state);
  }

  // Runtime events (tool activity, heartbeats, cron work) keep the displayed
  // state alive; without them the actor decays to sleeping.
  noteActivity(id, ctx = "", tool = "") {
    const actor = this.get(id);
    if (!actor) return;
    actor.noteActivity();
    const context = String(ctx || "").toLowerCase();
    const chatty = ["thinking", "talking", "reporting", "error"].includes(actor.state);
    const resting = actor.state === "sleeping" || actor.state === "idle";
    if (context.startsWith("cron") || context.startsWith("task") ||
        context.startsWith("heartbeat")) {
      if (!chatty) actor.setState("working_scheduled");
    } else if (context === "chat" || context.startsWith("inbox") ||
        context.startsWith("message")) {
      if (resting) actor.setState("thinking");
    } else if (resting) {
      // Unknown context but the runtime is clearly doing something.
      actor.setState("working_scheduled");
    }
    const label = labelForTool(tool);
    if (label) actor.setActivityLabel(label);
  }

  update(deltaSeconds) {
    this.actors.forEach((actor) => actor.update(deltaSeconds));
  }

  movingCount() {
    return [...this.actors.values()].filter((actor) => !actor.isSeated).length;
  }

  reservedTile(id) {
    const key = this.actorReservations.get(String(id || "").toLowerCase());
    return key ? key.split(",").map(Number) : null;
  }

  releaseDestination(id) {
    const actorId = String(id || "").toLowerCase();
    const key = this.actorReservations.get(actorId);
    if (key && this.destinationReservations.get(key) === actorId) {
      this.destinationReservations.delete(key);
    }
    this.actorReservations.delete(actorId);
  }

  destinationIsFree(point, actorId) {
    for (const [key, owner] of this.destinationReservations) {
      if (owner === actorId) continue;
      const [x, y] = key.split(",").map(Number);
      if (Math.max(Math.abs(point[0] - x), Math.abs(point[1] - y)) < 2) return false;
    }
    for (const actor of this.actors.values()) {
      if (actor.id === actorId || actor.isSeated) continue;
      const x = Math.round(actor.x / this.tile - 0.5);
      const y = Math.round(actor.y / this.tile - 1);
      if (Math.max(Math.abs(point[0] - x), Math.abs(point[1] - y)) < 2) return false;
    }
    return true;
  }

  reserveDestination(id, targetTile, alternatives = []) {
    const actorId = String(id || "").toLowerCase();
    this.releaseDestination(actorId);
    const seen = new Set();
    const candidates = [targetTile, ...alternatives, ...this.waypoints].filter((point) => {
      if (!Array.isArray(point) || point.length < 2) return false;
      if (this.scene.background_mode?.enabled && point[1] < 6) return false;
      const key = tileKey(...point);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    const selected = candidates.find((point) => this.destinationIsFree(point, actorId));
    if (!selected) return null;
    const key = tileKey(...selected);
    this.destinationReservations.set(key, actorId);
    this.actorReservations.set(actorId, key);
    return [...selected];
  }

  async walkTo(id, targetTile, options = {}) {
    const actor = this.get(id);
    if (!actor) return false;
    const finalTarget = options.reserveDestination === false
      ? targetTile
      : this.reserveDestination(id, targetTile, options.alternatives || []);
    if (!finalTarget) return false;
    const start = actor.isSeated ? [...actor.homeTile] : [
      Math.round(actor.x / this.tile - 0.5),
      Math.round(actor.y / this.tile - 1),
    ];
    const targetCompany = options.targetCompany || null;
    const mustCross = !this.scene.background_mode?.enabled &&
      targetCompany && targetCompany !== actor.company &&
      actor.company !== "human" && targetCompany !== "human";
    const pathRect = this.scene.zones.path?.rect;
    const pathEntry = pathRect
      ? [Math.floor((pathRect[0] + pathRect[2]) / 2), pathRect[1] + 1]
      : null;
    const destinations = [
      ...(mustCross
        ? [this.scene.walk.cross_company_via, ...(pathEntry ? [pathEntry] : [])]
        : []),
      ...(options.via || []),
      finalTarget,
    ];
    let cursor = start;
    for (const destination of destinations) {
      const path = findPath(cursor, destination, this.blocked, this.scene);
      const completed = await actor.walk(path, options.speed || 150);
      if (!completed) {
        this.releaseDestination(id);
        return false;
      }
      cursor = destination;
    }
    return true;
  }

  async returnHome(id, options = {}) {
    const actor = this.get(id);
    if (!actor) return false;
    this.releaseDestination(id);
    const completed = await this.walkTo(id, actor.homeTile, {
      speed: 155,
      ...options,
      reserveDestination: false,
    });
    if (!completed) return false;
    const seated = await actor.walkToSeat(options.speed || 155);
    if (seated) actor.sit();
    return seated;
  }
}

export { normalizeState, findPath };
