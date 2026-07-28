import { SpriteSheet } from "./sprite.js";
import { drawPixelText, measurePixelText } from "./pixel-text.js";

const STATE_MAP = Object.freeze({
  idle: { animation: "idle", bubble: "bubble_break" },
  working: { animation: "working", bubble: "bubble_working" },
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
  if (state.includes("bootstrap") || state.includes("think") || state.includes("process")) return "thinking";
  if (state.includes("work") || state.includes("busy") || state.includes("running")) return "working";
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
      if (x < 1 || x >= width - 1 || y < 4 || y >= height - 1) continue;
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
    this.state = "idle";
    this.bubble = "";
    this.bubbleOverride = "";
    this.bubbleOverrideRemaining = 0;
    this.fxTime = 0;
    this.motion = null;
    this.isSeated = true;
  }

  setState(value) {
    this.state = normalizeState(value);
    const mapping = STATE_MAP[this.state];
    this.bubble = mapping.bubble;
    if (!this.motion) {
      this.sprite.setAnimation(this.isSeated ? mapping.animation : "walk_down");
    }
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
    return this.walkPixels([{ ...this.seatPosition }], speed);
  }

  walkPixels(points, speed = 120) {
    if (this.motion?.resolve) this.motion.resolve(false);
    if (!points.length) return Promise.resolve(true);
    return new Promise((resolve) => {
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
    if (this.bubbleOverrideRemaining > 0) {
      this.bubbleOverrideRemaining = Math.max(0, this.bubbleOverrideRemaining - deltaSeconds);
      if (this.bubbleOverrideRemaining === 0) this.bubbleOverride = "";
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

  draw(ctx) {
    const spriteY = this.y - (this.isSeated && this.state === "sleeping" ? 14 : 0);
    ctx.save();
    ctx.globalAlpha = 0.18;
    ctx.fillStyle = "#1b1218";
    ctx.beginPath();
    ctx.ellipse(
      Math.round(this.x),
      Math.round(spriteY - 2),
      Math.max(18, Math.round(this.sprite.frameW * (this.isSeated ? 0.22 : 0.27))),
      Math.max(5, Math.round(this.sprite.frameH * 0.065)),
      0,
      0,
      Math.PI * 2,
    );
    ctx.fill();
    ctx.restore();
    this.sprite.draw(ctx, this.x, spriteY, 1);
  }

  drawStatusOverlay(ctx, options = {}) {
    const spriteY = this.y - (this.isSeated && this.state === "sleeping" ? 14 : 0);
    if (this.hasFullBubble()) {
      this.drawBubble(ctx, this.currentBubble(), spriteY, {
        offsetY: options.bubbleOffsetY || 0,
        offsetX: options.bubbleOffsetX || 0,
      });
    }
    this.drawStateAccent(ctx, spriteY);
  }

  drawNameOverlay(ctx, options = {}) {
    const position = {
      ...(options.namePosition || {}),
      offsetY: options.nameOffsetY || 0,
    };
    this.drawName(ctx, position);
    if (this.isCompactStatus()) this.drawStatusDot(ctx, position);
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
      width: width + (this.isCompactStatus() ? 12 : 2),
      height: 11,
    };
  }

  bubbleBounds(name = this.currentBubble(), spriteY = this.y, offsetY = 0, offsetX = 0) {
    const definition = this.assets.fxDefinition(name, name);
    const width = definition.frameW;
    const height = definition.frameH;
    const x = Math.round(this.x - width / 2 + offsetX);
    const headTop = this.headTop(spriteY);
    const tailBottom = definition.frameH - 3;
    const y = Math.round(
      headTop - 8 - tailBottom + Math.sin(this.fxTime * 3) * 2 + offsetY,
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
    ctx.fillStyle = COMPACT_STATUS_COLORS[this.state];
    ctx.fillRect(x + 1, y + 1, 6, 6);
    ctx.restore();
  }

  drawBubble(ctx, name, spriteY, options = {}) {
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

  headTop(spriteY) {
    const headInset = {
      thinking: 5,
      talking: 6,
      reporting: 6,
      sleeping: 28,
      error: 6,
    }[this.state] || 10;
    return spriteY - this.sprite.frameH + headInset;
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
    this.blocked = buildBlocked(scene);
    this.actors = new Map();
    this.destinationReservations = new Map();
    this.actorReservations = new Map();
    this.waypoints = waypointCandidates(scene);
  }

  initialize(animas = []) {
    const known = new Map(animas.map((anima) => [
      String(anima.name || anima.id).toLowerCase(),
      anima,
    ]));
    for (const [id, desk] of Object.entries(this.scene.desks || {})) {
      const home = [desk.tile[0], desk.tile[1] + 2];
      const deskFootY = (desk.tile[1] + 2) * this.tile;
      const isHuman = desk.is_human || id === (this.scene.human_id || "human");
      const deskAsset = this.assets.prop(isHuman ? "desk_taka" : "desk");
      const deskHeight = deskAsset.naturalHeight || deskAsset.height || (isHuman ? 80 : 72);
      const seatPosition = {
        x: desk.tile[0] * this.tile + this.tile / 2 + (desk.seat_offset_x ?? 12),
        y: deskFootY - (desk.seat_sink ?? 30),
      };
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
        },
      );
      actor.setState(known.get(id)?.status || "idle");
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
    const mustCross = targetCompany && targetCompany !== actor.company &&
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
