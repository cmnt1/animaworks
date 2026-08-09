import { drawPixelText, measurePixelText } from "./pixel-text.js";

const MAX_ACTIVE = 5;
const MAX_QUEUED = 5;

function unique(values) {
  return [...new Set(values.filter(Boolean).map((value) => String(value).toLowerCase()))];
}

function safeSummary(value, fallback = "新しい指示") {
  const summary = String(value || fallback)
    .replaceAll(/[\r\n\t]+/g, " ")
    .replaceAll(/\s+/g, " ")
    .trim();
  return (summary || fallback).slice(0, 32);
}

function positionFor(scene, actors, id) {
  const actor = actors.get(id);
  if (actor) return { x: actor.x, y: actor.y - 21 };
  const desk = scene.desks[id] || scene.desks[scene.human_id || "human"] ||
    Object.values(scene.desks)[0];
  return {
    x: (desk.tile[0] + 0.5) * scene.canvas.tile,
    y: (desk.tile[1] + 1) * scene.canvas.tile,
  };
}

function pathTiles(scene) {
  const path = scene.zones.path?.rect || [18, 14, 21, 22];
  const x = Math.floor((path[0] + path[2]) / 2);
  return {
    top: [x, path[1] + 1],
    middle: [x, Math.floor((path[1] + path[3]) / 2)],
    bottom: [x, path[3] - 1],
  };
}

function positionForTile(scene, tile) {
  return {
    x: (tile[0] + 0.5) * scene.canvas.tile,
    y: (tile[1] + 0.25) * scene.canvas.tile,
  };
}

function jstHour() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Tokyo",
    hour: "2-digit",
    hour12: false,
  }).formatToParts(new Date());
  return Number(parts.find((part) => part.type === "hour")?.value || 12) % 24;
}

export class Director {
  constructor(scene, assets, actors, renderer, controls = {}) {
    this.scene = scene;
    this.assets = assets;
    this.actors = actors;
    this.renderer = renderer;
    this.queue = [];
    this.active = new Set();
    this.effects = [];
    this.instructions = [];
    this.manualLighting = false;
    this.mode = "day";
    this.dayNightButton = controls.dayNightButton || null;
    this.applyAutomaticLighting();
    this.dayNightButton?.addEventListener("click", () => this.toggleLighting());
  }

  dispatch(type, payload = {}) {
    const normalized = String(type || "").toLowerCase().replaceAll(".", "_");
    const handlers = {
      message_sent: () => this.envelope(payload),
      dm_sent: () => this.envelope(payload),
      delegation: () => this.meeting(payload),
      board_post: () => this.meeting(payload),
      instruction: () => this.instruction(payload),
      human_instruction: () => this.instruction(payload),
      external_out: () => this.delivery(payload),
      report_out: () => this.delivery(payload),
      heartbeat: () => this.heartbeat(payload),
    };
    if (!handlers[normalized]) return false;
    this.enqueue(normalized, handlers[normalized]);
    return true;
  }

  enqueue(name, run) {
    this.queue.push({ name, run });
    while (this.queue.length > MAX_QUEUED) this.queue.shift();
    this.pump();
  }

  pump() {
    while (this.active.size < MAX_ACTIVE && this.queue.length) {
      const job = this.queue.shift();
      const task = Promise.resolve()
        .then(job.run)
        .catch((error) => {
          window.__pixelErrors?.push(`director:${job.name}: ${error?.stack || error}`);
        })
        .finally(() => {
          this.active.delete(task);
          this.pump();
        });
      this.active.add(task);
    }
  }

  update(deltaSeconds) {
    for (const effect of this.effects) {
      effect.elapsed += deltaSeconds;
      if (effect.follow) {
        const actor = this.actors.get(effect.follow);
        if (actor) {
          effect.x = actor.x;
          effect.y = actor.y - 45;
        }
      }
    }
    const completed = this.effects.filter((effect) => effect.elapsed >= effect.duration);
    this.effects = this.effects.filter((effect) => effect.elapsed < effect.duration);
    completed.forEach((effect) => effect.resolve?.());
  }

  addEffect(effect) {
    return new Promise((resolve) => {
      this.effects.push({
        elapsed: 0,
        duration: 1,
        ...effect,
        resolve,
      });
    });
  }

  pause(duration) {
    return this.addEffect({ type: "pause", duration });
  }

  async envelope(payload) {
    const animaIds = this.actors.ids({ includeHuman: false });
    const humanId = this.scene.human_id || "human";
    const from = String(payload.from || payload.from_person || payload.name || humanId).toLowerCase();
    const to = String(payload.to || payload.to_person || payload.target || animaIds[0] || humanId).toLowerCase();
    const points = [positionFor(this.scene, this.actors, from)];
    const fromCompany = this.actors.companyOf(from);
    const toCompany = this.actors.companyOf(to);
    if (fromCompany !== toCompany && fromCompany !== "human" && toCompany !== "human") {
      points.push(positionForTile(this.scene, pathTiles(this.scene).middle));
      points.push(positionFor(this.scene, this.actors, humanId));
    }
    points.push(positionFor(this.scene, this.actors, to));
    await this.addEffect({ type: "envelope", points, duration: points.length > 2 ? 2.2 : 1.35 });
    await this.addEffect({
      type: "burst",
      x: points.at(-1).x,
      y: points.at(-1).y,
      duration: 0.45,
      color: "#fff0a8",
    });
  }

  async meeting(payload) {
    const participants = unique(
      payload.participants || [payload.from, payload.from_person, payload.to, payload.to_person, payload.name],
    ).filter((id) => this.actors.get(id)).slice(0, 2);
    if (!participants.length) return;
    const company = this.actors.companyOf(participants[0]);
    const table = Object.values(this.scene.props).find(
      (prop) => prop.kind === "meeting" && prop.company === company,
    ) || Object.values(this.scene.props).find((prop) => prop.kind === "meeting");
    if (!table) return;
    const [tableX, tableY] = table.tile;
    const slots = [
      [tableX - 1, tableY], [tableX + table.w, tableY],
      [tableX, tableY + table.h], [tableX + table.w - 1, tableY + table.h],
      [tableX - 1, tableY + 1],
    ];
    const previous = new Map(participants.map((id) => [id, this.actors.get(id).state]));
    const arrivals = await Promise.all(participants.map((id, index) => this.actors.walkTo(
      id,
      slots[index % slots.length],
      { targetCompany: company, speed: 165, alternatives: slots },
    )));
    const arrived = participants.filter((id, index) => arrivals[index]);
    if (!arrived.length) return;
    arrived.forEach((id) => this.actors.setState(id, "talking"));
    await this.addEffect({
      type: "talk",
      x: (table.tile[0] + table.w / 2) * this.scene.canvas.tile,
      y: table.tile[1] * this.scene.canvas.tile - 10,
      label: "打合せ中",
      duration: 3,
    });
    await Promise.all(arrived.map((id) => this.actors.returnHome(id)));
    participants.forEach((id) => this.actors.setState(id, previous.get(id)));
  }

  async delivery(payload) {
    const id = String(
      payload.name || payload.from || payload.actor ||
      this.actors.ids({ includeHuman: false })[0] || "",
    ).toLowerCase();
    const actor = this.actors.get(id);
    if (!actor) return;
    const previous = actor.state;
    this.actors.setState(id, "reporting");
    actor.setTransientBubble("bubble_delivery", 30);
    const route = pathTiles(this.scene);
    const entrance = this.scene.zones.entrance?.rect;
    const door = this.scene.props.door_frame || {
      tile: [
        entrance ? Math.floor((entrance[0] + entrance[2] - 5) / 2) : 17,
        Math.floor(this.scene.canvas.h / this.scene.canvas.tile) - 3,
      ],
      w: 6,
      h: 4,
      bottom_inset: 64,
    };
    const handoff = door.service_tile || [door.tile[0] + door.w - 1, door.tile[1] - 1];
    const arrived = await this.actors.walkTo(id, handoff, {
      speed: 165,
      via: [route.top, route.middle, route.bottom],
      alternatives: [
        [handoff[0] - 2, handoff[1]],
        [handoff[0], handoff[1] - 2],
      ],
    });
    if (!arrived) {
      actor.clearTransientBubble();
      this.actors.setState(id, previous);
      return;
    }
    const customerX = (door.tile[0] + door.w / 2) * this.scene.canvas.tile;
    const customerY = this.scene.canvas.h - (door.bottom_inset ?? 64);
    const handoffPosition = positionForTile(this.scene, this.actors.reservedTile(id) || handoff);
    await Promise.all([
      this.addEffect({
        type: "customer",
        variant: Math.random() < 0.5 ? "customer_a" : "customer_b",
        fromX: customerX,
        fromY: customerY,
        // Stop short of the anima so the sprites face each other
        // instead of overlapping on the same tile.
        x: handoffPosition.x,
        y: handoffPosition.y + 39,
        duration: 2.4,
      }),
      this.addEffect({
        type: "package",
        fromX: actor.x,
        fromY: actor.y - 21,
        x: handoffPosition.x,
        y: handoffPosition.y - 23,
        duration: 1.2,
      }),
    ]);
    await this.addEffect({ type: "heart", x: handoffPosition.x, y: handoffPosition.y - 48, duration: 0.9 });
    this.actors.setState(id, "success");
    await this.pause(0.65);
    await this.actors.returnHome(id, { via: [route.middle, route.top] });
    actor.clearTransientBubble();
    this.actors.setState(id, previous);
  }

  async instruction(payload) {
    const summary = safeSummary(payload.summary || payload.label || payload.instruction);
    this.instructions.push(summary);
    this.instructions = this.instructions.slice(-3);
    this.renderer.setInstructions(this.instructions);
    const humanId = this.scene.human_id || "human";
    this.renderer.flashHuman();
    this.actors.get(humanId)?.setTransientBubble("bubble_instruction", 1.4);
    const human = positionFor(this.scene, this.actors, humanId);
    await this.addEffect({ type: "burst", x: human.x, y: human.y - 13, duration: 1.2, color: "#ffe777" });
  }

  async heartbeat(payload) {
    const id = String(
      payload.name || payload.actor || payload.target ||
      this.actors.ids({ includeHuman: false })[0] || "",
    ).toLowerCase();
    const actor = this.actors.get(id);
    if (!actor) return;
    await this.addEffect({ type: "heart", follow: id, x: actor.x, y: actor.y - 68, duration: 0.9 });
  }

  applyAutomaticLighting() {
    if (this.manualLighting) return;
    const hour = jstHour();
    this.setLighting(hour >= 7 && hour < 19 ? "day" : "night");
  }

  toggleLighting() {
    this.manualLighting = true;
    this.setLighting(this.mode === "day" ? "night" : "day");
  }

  setLighting(mode) {
    this.mode = mode === "night" ? "night" : "day";
    this.renderer.setLighting(this.mode);
    if (this.dayNightButton) {
      const icon = this.dayNightButton.querySelector("#dayNightIcon");
      const label = this.dayNightButton.querySelector("#dayNightLabel");
      if (icon) icon.src = this.mode === "day" ? "assets/fx/sun.png" : "assets/fx/moon.png";
      if (label) label.textContent = this.mode === "day" ? "昼" : "夜";
      this.dayNightButton.dataset.mode = this.mode;
    }
  }

  draw(ctx) {
    for (const effect of this.effects) {
      if (effect.type === "pause" || effect.type === "customer") continue;
      const progress = Math.min(1, effect.elapsed / effect.duration);
      if (effect.type === "envelope") this.drawEnvelope(ctx, effect, progress);
      else if (effect.type === "heart") this.drawHeart(ctx, effect, progress);
      else if (effect.type === "burst") this.drawBurst(ctx, effect, progress);
      else if (effect.type === "talk") this.drawTalk(ctx, effect, progress);
      else if (effect.type === "package") this.drawPackage(ctx, effect, progress);
    }
  }

  customerLayers(ctx) {
    return this.effects
      .filter((effect) => effect.type === "customer")
      .map((effect) => {
        const progress = Math.min(1, effect.elapsed / effect.duration);
        const { y } = this.customerPosition(effect, progress);
        return {
          y,
          priority: 0,
          draw: () => this.drawCustomer(ctx, effect, progress),
        };
      });
  }

  customerPosition(effect, progress) {
    const trip = progress < 0.5 ? progress * 2 : (1 - progress) * 2;
    return {
      x: effect.fromX + (effect.x - effect.fromX) * trip,
      y: effect.fromY + (effect.y - effect.fromY) * trip,
    };
  }

  drawEnvelope(ctx, effect, progress) {
    const segments = effect.points.length - 1;
    const scaled = Math.min(segments - 0.0001, progress * segments);
    const index = Math.floor(scaled);
    const local = scaled - index;
    const from = effect.points[index];
    const to = effect.points[index + 1];
    const x = from.x + (to.x - from.x) * local;
    const y = from.y + (to.y - from.y) * local - Math.sin(local * Math.PI) * 72;
    const definition = this.assets.fxDefinition("envelope", "✉");
    const frame = Math.floor(effect.elapsed * definition.fps) % definition.frames;
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

  drawHeart(ctx, effect, progress) {
    const scale = Math.sin(progress * Math.PI) * 1.4;
    const y = effect.y - progress * 18;
    ctx.save();
    ctx.translate(Math.round(effect.x), Math.round(y));
    ctx.scale(scale, scale);
    ctx.fillStyle = "#ef6578";
    ctx.fillRect(-7, -5, 14, 10);
    ctx.fillRect(-5, 5, 10, 5);
    ctx.fillRect(-4, -8, 5, 5);
    ctx.fillRect(3, -8, 5, 5);
    ctx.restore();
  }

  drawBurst(ctx, effect, progress) {
    const radius = 10 + progress * 34;
    ctx.save();
    ctx.globalAlpha = 1 - progress;
    ctx.strokeStyle = effect.color || "#fff0a8";
    ctx.lineWidth = 4;
    for (let index = 0; index < 8; index += 1) {
      const angle = index * Math.PI / 4;
      ctx.beginPath();
      ctx.moveTo(effect.x + Math.cos(angle) * radius * 0.45, effect.y + Math.sin(angle) * radius * 0.45);
      ctx.lineTo(effect.x + Math.cos(angle) * radius, effect.y + Math.sin(angle) * radius);
      ctx.stroke();
    }
    ctx.restore();
  }

  drawTalk(ctx, effect, progress) {
    // Programmatic bubble matching former bubble_meeting ("打合せ中") row.
    const label = "打合せ中";
    const border = "#248a9b";
    const fill = "#fbf0e4";
    const textColor = "#248a9b";
    const width = Math.max(40, measurePixelText(label, { scale: 1, bold: true }) + 18);
    const height = 24;
    const bodyHeight = height - 6;
    const bob = Math.sin(progress * Math.PI * 10) * 3;
    const x = Math.round(effect.x - width / 2);
    const y = Math.round(effect.y + bob);
    const tailX = Math.round(x + width / 2);
    ctx.save();
    ctx.fillStyle = border;
    ctx.fillRect(x + 2, y, width - 4, bodyHeight);
    ctx.fillRect(x, y + 2, width, bodyHeight - 4);
    ctx.fillStyle = fill;
    ctx.fillRect(x + 3, y + 2, width - 6, bodyHeight - 4);
    ctx.fillRect(x + 2, y + 3, width - 4, bodyHeight - 6);
    ctx.fillStyle = border;
    ctx.fillRect(tailX - 4, y + bodyHeight, 8, 2);
    ctx.fillRect(tailX - 2, y + bodyHeight + 2, 4, 2);
    ctx.fillStyle = fill;
    ctx.fillRect(tailX - 3, y + bodyHeight - 1, 6, 2);
    drawPixelText(ctx, label, tailX, y + Math.round(bodyHeight / 2), {
      scale: 1,
      bold: true,
      align: "center",
      baseline: "middle",
      color: textColor,
    });
    ctx.restore();
  }

  drawCustomer(ctx, effect, progress) {
    const visible = Math.min(1, progress * 5, (1 - progress) * 5);
    const { x, y } = this.customerPosition(effect, progress);
    const definition = this.assets.character(effect.variant || "customer_a");
    const animation = definition.anims[progress < 0.5 ? "walk_up" : "walk_down"];
    const frame = Math.floor(effect.elapsed * animation.fps) % animation.frames;
    // Walking characters render at 1.5x, so the visiting customer matches.
    const scale = 1.5;
    const door = this.scene.props.door_frame;
    const doorImage = this.assets.prop("door_frame", 192, 112);
    const doorWidth = doorImage.naturalWidth || doorImage.width || 192;
    const doorHeight = doorImage.naturalHeight || doorImage.height || 112;
    const doorBottom = this.scene.canvas.h - (door?.bottom_inset ?? 64);
    const doorTop = doorBottom - doorHeight;
    const doorX = (door?.tile?.[0] ?? 17) * this.scene.canvas.tile;
    const crossingThreshold = doorBottom - 21;
    ctx.save();
    if (y > crossingThreshold) {
      ctx.beginPath();
      ctx.rect(
        doorX + Math.round(doorWidth * 0.24),
        doorTop + Math.round(doorHeight * 0.25),
        Math.round(doorWidth * 0.48),
        Math.round(doorHeight * 0.75),
      );
      ctx.clip();
    }
    ctx.globalAlpha = visible * 0.18;
    ctx.fillStyle = "#1a1116";
    ctx.beginPath();
    ctx.ellipse(x, y - 2, 17 * scale, 4 * scale, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = visible;
    ctx.drawImage(
      definition.image,
      frame * definition.frameW,
      animation.row * definition.frameH,
      definition.frameW,
      definition.frameH,
      Math.round(x - (definition.frameW * scale) / 2),
      Math.round(y - definition.frameH * scale),
      definition.frameW * scale,
      definition.frameH * scale,
    );
    ctx.restore();
    ctx.save();
    ctx.globalAlpha = visible;
    drawPixelText(ctx, "guest", x, y + 2, {
      scale: 1,
      align: "center",
      color: "#fff6dc",
      shadow: "#60432e",
    });
    ctx.restore();
  }

  drawPackage(ctx, effect, progress) {
    const x = effect.fromX + (effect.x - effect.fromX) * progress;
    const y = effect.fromY + (effect.y - effect.fromY) * progress - Math.sin(progress * Math.PI) * 20;
    ctx.fillStyle = "#b77b49";
    ctx.fillRect(x - 11, y - 9, 22, 18);
    ctx.strokeStyle = "#5d3e31";
    ctx.strokeRect(x - 11, y - 9, 22, 18);
    ctx.fillStyle = "#f1c879";
    ctx.fillRect(x - 2, y - 9, 4, 18);
  }
}

export { safeSummary, MAX_ACTIVE, MAX_QUEUED };
