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
    if (!this.motion) this.sprite.setAnimation(mapping.animation);
  }

  walk(path, speed = 120) {
    if (this.motion?.resolve) this.motion.resolve(false);
    const points = path.slice(1).map(([x, y]) => ({
      x: (x + 0.5) * this.tileSize,
      y: (y + 1) * this.tileSize,
    }));
    if (!points.length) return Promise.resolve(true);
    return new Promise((resolve) => {
      this.isSeated = false;
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
          this.sprite.setAnimation(mapping.animation);
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
    const spriteY = this.y + (this.isSeated && this.state === "sleeping" ? 8 : 0);
    ctx.save();
    ctx.globalAlpha = 0.18;
    ctx.fillStyle = "#1b1218";
    ctx.beginPath();
    ctx.ellipse(
      Math.round(this.x),
      Math.round(spriteY - 2),
      Math.max(18, Math.round(this.sprite.frameW * 0.27)),
      Math.max(5, Math.round(this.sprite.frameH * 0.065)),
      0,
      0,
      Math.PI * 2,
    );
    ctx.fill();
    ctx.restore();
    this.sprite.draw(ctx, this.x, spriteY, 1);
    if (!this.isSeated) this.drawName(ctx);
    const bubble = this.bubbleOverride || this.bubble || STATE_MAP[this.state]?.bubble || "bubble_break";
    const quiet = !this.bubbleOverride && bubble === "bubble_break";
    this.drawBubble(ctx, bubble, spriteY, { quiet });
    this.drawStateAccent(ctx, spriteY);
  }

  drawName(ctx, position = {}) {
    ctx.save();
    const textOptions = { fontSize: 4, scale: 2, bold: true };
    const width = Math.max(36, measurePixelText(this.id, textOptions) + 8);
    const x = Math.round(position.x ?? this.x);
    const y = Math.round(position.y ?? this.y + 3);
    ctx.fillStyle = "#573722";
    ctx.fillRect(x - width / 2 - 1, y, width + 2, 16);
    ctx.fillStyle = "#f3dfb5";
    ctx.fillRect(x - width / 2, y + 1, width, 14);
    drawPixelText(ctx, this.id, x, y + 8, {
      ...textOptions,
      align: "center",
      baseline: "middle",
      color: "#493020",
    });
    ctx.restore();
  }

  drawBubble(ctx, name, spriteY, options = {}) {
    const definition = this.assets.fxDefinition(name, name);
    const frame = Math.floor(this.fxTime * definition.fps) % definition.frames;
    const scale = 1;
    const width = Math.round(definition.frameW * scale);
    const height = Math.round(definition.frameH * scale);
    const x = Math.round(this.x - width / 2);
    const headTop = this.headTop(spriteY);
    const tailBottom = Math.round((definition.frameH - 3) * scale);
    const y = Math.round(headTop - 8 - tailBottom + Math.sin(this.fxTime * 3) * 2);
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
  }

  initialize(animas = []) {
    const known = new Map(animas.map((anima) => [
      String(anima.name || anima.id).toLowerCase(),
      anima,
    ]));
    for (const [id, desk] of Object.entries(this.scene.desks || {})) {
      const home = [desk.tile[0], desk.tile[1] + 2];
      const deskFootY = (desk.tile[1] + 2) * this.tile;
      const seatPosition = {
        x: desk.tile[0] * this.tile + this.tile / 2,
        y: deskFootY - 26,
      };
      const actor = new Actor(
        id,
        this.assets.character(id),
        home,
        this.tile,
        seatPosition,
        this.assets,
        {
          company: desk.company || known.get(id)?.company || "default",
          isHuman: desk.is_human || id === (this.scene.human_id || "human"),
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

  async walkTo(id, targetTile, options = {}) {
    const actor = this.get(id);
    if (!actor) return false;
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
      targetTile,
    ];
    let cursor = start;
    for (const destination of destinations) {
      const path = findPath(cursor, destination, this.blocked, this.scene);
      const completed = await actor.walk(path, options.speed || 150);
      if (!completed) return false;
      cursor = destination;
    }
    return true;
  }

  async returnHome(id, options = {}) {
    const actor = this.get(id);
    if (!actor) return false;
    const completed = await this.walkTo(id, actor.homeTile, { speed: 155, ...options });
    if (completed) actor.sit();
    return completed;
  }
}

export { normalizeState, findPath };
