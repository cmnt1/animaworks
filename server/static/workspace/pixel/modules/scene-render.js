import { drawPixelText, measurePixelText } from "./pixel-text.js";

function rectFromZone(zone, tile) {
  const [x1, y1, x2, y2] = zone.rect;
  return [x1 * tile, y1 * tile, (x2 - x1 + 1) * tile, (y2 - y1 + 1) * tile];
}

function drawGroundShadow(ctx, x, y, radiusX, radiusY = 5) {
  ctx.save();
  ctx.globalAlpha = 0.18;
  ctx.fillStyle = "#1a1116";
  ctx.beginPath();
  ctx.ellipse(Math.round(x), Math.round(y), radiusX, radiusY, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function floorVariation(x, y, floorName) {
  let seed = Math.imul(x + 17, 73856093) ^ Math.imul(y + 31, 19349663);
  for (const character of floorName) seed = Math.imul(seed ^ character.charCodeAt(0), 83492791);
  return ((seed >>> 0) % 7 - 3) / 100;
}

function stableHash(value) {
  let hash = 2166136261;
  for (const character of value) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

export class SceneRenderer {
  constructor(canvas, scene, assets) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d", { alpha: false });
    this.ctx.imageSmoothingEnabled = false;
    this.scene = scene;
    this.assets = assets;
    this.tile = scene.canvas.tile;
    this.mode = "day";
    this.instructions = [];
    this.humanFlash = 0;
    this.signDate = new Intl.DateTimeFormat("ja-JP", {
      month: "2-digit",
      day: "2-digit",
      weekday: "short",
    }).format(new Date());
    const catProp = scene.props.cat;
    this.cat = catProp ? {
      x: (catProp.tile[0] + 0.5) * this.tile,
      y: (catProp.tile[1] + 1) * this.tile,
      targetX: (catProp.tile[0] + 0.5) * this.tile,
      targetY: (catProp.tile[1] + 1) * this.tile,
      nextMove: 5,
      moving: false,
    } : null;
    canvas.width = scene.canvas.w;
    canvas.height = scene.canvas.h;
  }

  setLighting(mode) {
    this.mode = mode === "night" ? "night" : "day";
  }

  setInstructions(lines) {
    this.instructions = lines.slice(-3);
  }

  flashHuman(duration = 1.4) {
    this.humanFlash = Math.max(this.humanFlash, duration);
  }

  update(deltaSeconds) {
    this.humanFlash = Math.max(0, this.humanFlash - deltaSeconds);
    this.updateCat(deltaSeconds);
  }

  draw(actors, director, timeSeconds = 0) {
    const { ctx } = this;
    ctx.imageSmoothingEnabled = false;
    this.drawFloor();
    this.drawHumanPlatform();
    this.drawPathChevrons();
    this.drawWalls();
    const { under, layers } = this.buildFurnitureLayers(timeSeconds, actors);
    under.sort((a, b) => a.y - b.y).forEach((layer) => layer.draw());

    for (const actor of actors.values()) {
      const desk = this.scene.desks[actor.id];
      const deskFootY = desk ? (desk.tile[1] + 2) * this.tile : actor.y;
      layers.push({
        y: actor.isSeated
          ? deskFootY + (actor.state === "sleeping" ? 1 : -1)
          : actor.y,
        draw: () => actor.draw(ctx),
      });
    }
    if (this.cat) {
      layers.push({
        y: this.cat.y,
        draw: () => this.drawCat(),
      });
    }
    layers.sort((a, b) => a.y - b.y);
    layers.forEach((layer) => layer.draw());

    this.drawStaticLabels();
    this.drawHumanGlass();
    this.drawWhiteboardText();
    this.drawHangingSign();
    director?.draw(ctx);
    this.drawLighting();
    this.drawPaletteUnifier();
  }

  drawFloor() {
    const { ctx, tile } = this;
    ctx.fillStyle = "#c9a875";
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    const floorColors = {
      wood_warm: ["#dcbf8b", "#d4b37d"],
      wood_cool: ["#c4b8a2", "#b9ab94"],
      carpet_blue: ["#8a9aae", "#8493a5"],
      mat: ["#aa7f69", "#9d725e"],
    };
    const cells = new Map();
    for (const [name, zone] of Object.entries(this.scene.zones)) {
      const floorName = name === "path"
        ? this.scene.zones.human?.floor || zone.floor
        : zone.floor;
      const group = name === "path" || name === "human" ? "human" : name;
      const [x1, y1, x2, y2] = zone.rect;
      for (let tileY = y1; tileY <= y2; tileY += 1) {
        for (let tileX = x1; tileX <= x2; tileX += 1) {
          cells.set(`${tileX},${tileY}`, { x: tileX, y: tileY, floorName, group });
        }
      }
    }

    for (const cell of cells.values()) {
      const px = cell.x * tile;
      const py = cell.y * tile;
      const colors = floorColors[cell.floorName] || floorColors.wood_warm;
      const tileImage = this.assets.tile(cell.floorName);
      ctx.globalAlpha = 1;
      if (tileImage) {
        ctx.drawImage(tileImage, px, py, tile, tile);
      } else {
        ctx.fillStyle = colors[(cell.x + cell.y) % 2];
        ctx.fillRect(px, py, tile, tile);
        ctx.fillStyle = "#fff1";
        ctx.fillRect(px, py, tile, 2);
        ctx.fillStyle = "#53351b12";
        ctx.fillRect(px, py + tile - 2, tile, 2);
      }
      const variation = floorVariation(cell.x, cell.y, cell.floorName);
      if (variation !== 0) {
        ctx.save();
        ctx.globalAlpha = Math.abs(variation);
        ctx.fillStyle = variation > 0 ? "#ffffff" : "#000000";
        ctx.fillRect(px, py, tile, tile);
        ctx.restore();
      }
    }

    const shadeEdge = (cell, side) => {
      const px = cell.x * tile;
      const py = cell.y * tile;
      const bands = [[0, 6, 0.065], [6, 9, 0.035], [15, 17, 0.015]];
      ctx.save();
      ctx.fillStyle = "#1f1520";
      for (const [offset, size, alpha] of bands) {
        ctx.globalAlpha = alpha;
        if (side === "left") ctx.fillRect(px + offset, py, size, tile);
        else if (side === "right") ctx.fillRect(px + tile - offset - size, py, size, tile);
        else if (side === "top") ctx.fillRect(px, py + offset, tile, size);
        else ctx.fillRect(px, py + tile - offset - size, tile, size);
      }
      ctx.restore();
    };
    for (const cell of cells.values()) {
      const neighbors = [
        ["left", cell.x - 1, cell.y],
        ["right", cell.x + 1, cell.y],
        ["top", cell.x, cell.y - 1],
        ["bottom", cell.x, cell.y + 1],
      ];
      for (const [side, x, y] of neighbors) {
        if (cells.get(`${x},${y}`)?.group !== cell.group) shadeEdge(cell, side);
      }
    }

    for (const [name, zone] of Object.entries(this.scene.zones)) {
      if (name === "path" || name === "human") continue;
      const [x, y, width, height] = rectFromZone(zone, tile);
      ctx.strokeStyle = "#45344399";
      ctx.lineWidth = 3;
      ctx.strokeRect(x + 1, y + 1, width - 2, height - 2);
    }
  }

  drawHumanPlatform() {
    const zone = this.scene.zones.human;
    if (!zone) return;
    const [x, y, width, height] = rectFromZone(zone, this.tile);
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = "#211925";
    ctx.globalAlpha = 0.22;
    ctx.fillRect(x + 6, y + height - 2, width - 6, 7);
    ctx.fillRect(x + width - 2, y + 6, 7, height - 6);
    ctx.restore();
  }

  drawPathChevrons() {
    const zone = this.scene.zones.path;
    if (!zone) return;
    const centerX = ((zone.rect[0] + zone.rect[2] + 1) / 2) * this.tile;
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = "#f2e4c5";
    ctx.globalAlpha = 0.16;
    for (let tileY = zone.rect[1] + 2; tileY < zone.rect[3]; tileY += 2) {
      const top = tileY * this.tile + 8;
      for (let step = 0; step < 4; step += 1) {
        ctx.fillRect(Math.round(centerX - 13 + step * 3), top + step * 2, 4, 2);
        ctx.fillRect(Math.round(centerX + 9 - step * 3), top + step * 2, 4, 2);
      }
    }
    ctx.restore();
  }

  drawHumanGlass() {
    const zone = this.scene.zones.human;
    if (!zone) return;
    const [x, y, width, height] = rectFromZone(zone, this.tile);
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = "#eaf8ff";
    ctx.globalAlpha = 0.035;
    ctx.fillRect(x + 3, y + 3, width - 6, height - 6);
    ctx.globalAlpha = 0.42;
    ctx.fillStyle = "#d9f2f5";
    ctx.fillRect(x, y, width, 2);
    ctx.fillRect(x, y, 2, height);
    ctx.fillRect(x + width - 2, y, 2, height);
    ctx.fillRect(x, y + height - 2, this.tile, 2);
    ctx.globalAlpha = 0.7;
    ctx.fillStyle = "#4c5960";
    ctx.fillRect(x - 2, y - 2, 5, 7);
    ctx.fillRect(x + width - 3, y - 2, 5, 7);
    ctx.fillRect(x - 2, y + height - 5, 5, 7);
    ctx.fillRect(x + width - 3, y + height - 5, 5, 7);
    for (let frameX = x + this.tile * 2; frameX < x + width; frameX += this.tile * 2) {
      ctx.globalAlpha = 0.28;
      ctx.fillRect(frameX, y, 2, height - this.tile);
    }
    ctx.restore();
  }

  drawWalls() {
    const { ctx, tile } = this;
    const wall = this.assets.wall(this.mode);
    ctx.fillStyle = "#3b2b38";
    ctx.fillRect(0, 0, this.canvas.width, tile);
    if (wall) {
      const half = this.canvas.width / 2;
      ctx.drawImage(wall, 0, 0, half, wall.naturalHeight, 0, tile, half, tile * 3);
      ctx.save();
      ctx.translate(this.canvas.width, 0);
      ctx.scale(-1, 1);
      ctx.drawImage(wall, half, 0, half, wall.naturalHeight, 0, tile, half, tile * 3);
      ctx.restore();
    } else {
      ctx.fillStyle = "#f0dec0";
      ctx.fillRect(0, tile, this.canvas.width, tile * 3);
      ctx.fillStyle = this.mode === "night" ? "#29365c" : "#9bd0df";
      for (let x = tile; x < this.canvas.width - tile; x += tile * 5) {
        ctx.fillRect(x, tile + 10, tile * 4, tile * 2);
      }
    }
    ctx.fillStyle = "#3d281f";
    ctx.fillRect(0, tile * 4 - 2, this.canvas.width, 1);
    ctx.fillStyle = "#c08b56";
    ctx.fillRect(0, tile * 4 - 1, this.canvas.width, 1);
  }

  drawStaticLabels() {
    const { ctx, tile } = this;
    for (const zone of Object.values(this.scene.zones)) {
      if (!zone.label) continue;
      const [x1, y1, x2] = zone.rect;
      if (y1 < 4) continue;
      ctx.save();
      const textOptions = { fontSize: 9, scale: 1, bold: true, bitmap: false };
      const width = measurePixelText(zone.label, textOptions) + 18;
      const zoneLeft = x1 * tile;
      const zoneRight = (x2 + 1) * tile;
      const x = Math.min(zoneRight - width - 8, zoneLeft + 40);
      const y = y1 * tile + 7;
      ctx.fillStyle = "#3e291f";
      ctx.fillRect(x - 2, y - 2, width + 4, 20);
      ctx.fillStyle = "#8b603c";
      ctx.fillRect(x, y, width, 16);
      ctx.fillStyle = "#c99a62";
      ctx.fillRect(x + 2, y + 2, width - 4, 2);
      drawPixelText(ctx, zone.label, x + 9, y + 3, {
        ...textOptions,
        color: "#fff0cd",
        shadow: "#3d281f",
        shadowX: 2,
        shadowY: 2,
      });
      ctx.restore();
    }
  }

  buildFurnitureLayers(timeSeconds, actors) {
    const { tile, scene, assets } = this;
    const layers = [];
    const under = [];

    for (const [id, desk] of Object.entries(scene.desks)) {
      const wide = desk.wide || 1;
      const width = wide > 1 ? 128 : 96;
      const height = wide > 1 ? 72 : 64;
      const footX = desk.tile[0] * tile + tile / 2;
      const footY = (desk.tile[1] + 2) * tile;
      const actor = actors.get(id);
      layers.push({
        y: footY - 2,
        draw: () => {
          const chair = assets.prop("chair", 32, 40);
          const chairW = chair.naturalWidth || chair.width || 32;
          const chairH = chair.naturalHeight || chair.height || 40;
          const seatY = actor?.seatPosition.y ?? footY - 22;
          drawGroundShadow(this.ctx, footX, seatY + 7, 12, 4);
          this.ctx.drawImage(chair, footX - chairW / 2, seatY - chairH + 9, chairW, chairH);
        },
      });
      layers.push({
        y: footY,
        draw: () => {
          const ctx = this.ctx;
          if (id === (scene.human_id || "human") && this.humanFlash > 0) {
            ctx.save();
            ctx.globalAlpha = 0.35 + Math.sin(timeSeconds * 14) * 0.18;
            ctx.fillStyle = "#ffe879";
            ctx.fillRect(footX - width / 2 - 8, footY - height - 8, width + 16, height + 16);
            ctx.restore();
          }
          drawGroundShadow(ctx, footX, footY - 3, width * 0.36, 7);
          const deskAsset = id === (scene.human_id || "human") ? "desk_human" : "desk";
          ctx.drawImage(assets.prop(deskAsset, width, height), footX - width / 2, footY - height, width, height);
          this.drawPersonalItem(desk.item || id, footX, footY, width, height);
          this.drawDeskClutter(id, footX, footY, width);
          if (actor?.isSeated) actor.drawName(ctx, { x: footX, y: footY - 15 });
        },
      });
    }

    for (const [name, prop] of Object.entries(scene.props)) {
      if (name === "plants" || name === "cat") continue;
      const width = prop.w * tile;
      const height = prop.h * tile;
      const x = prop.tile[0] * tile;
      const footY = (prop.tile[1] + prop.h) * tile;
      const assetName = prop.sprite || (prop.kind === "meeting" ? "meeting_table" : name);
      const target = prop.under ? under : layers;
      target.push({
        y: footY,
        draw: () => {
          if (name === "parcel_door" && !assets.images.has("scene.props.parcel_stack")) {
            this.drawParcelStack(x, footY, timeSeconds);
            return;
          }
          const image = assets.prop(assetName, width, height);
          const drawWidth = image.naturalWidth || image.width || width;
          const drawHeight = image.naturalHeight || image.height || height;
          if (!prop.under) {
            drawGroundShadow(this.ctx, x + drawWidth / 2, footY - 2, Math.max(8, drawWidth * 0.34), 5);
          }
          this.ctx.drawImage(image, x, footY - drawHeight, drawWidth, drawHeight);
          if (name === "server_rack") {
            this.ctx.fillStyle = Math.floor(timeSeconds * 4) % 2 ? "#6dff9a" : "#efba5e";
            this.ctx.fillRect(x + drawWidth - 15, footY - drawHeight + 12, 5, 5);
          }
        },
      });
    }

    for (const [xTile, yTile] of scene.props.plants || []) {
      const width = tile;
      const x = xTile * tile;
      const footY = (yTile + 1) * tile;
      layers.push({
        y: footY,
        draw: () => {
          const image = assets.prop("plant", width, 48);
          const drawWidth = image.naturalWidth || image.width || width;
          const drawHeight = image.naturalHeight || image.height || 48;
          drawGroundShadow(this.ctx, x + drawWidth / 2, footY - 2, 12, 4);
          this.ctx.drawImage(image, x, footY - drawHeight, drawWidth, drawHeight);
        },
      });
    }
    return { under, layers };
  }

  drawParcelStack(x, footY, timeSeconds) {
    const definition = this.assets.fxDefinition("parcel", "parcel");
    const frame = Math.floor(timeSeconds * definition.fps) % definition.frames;
    const ctx = this.ctx;
    drawGroundShadow(ctx, x + 18, footY - 2, 17, 4);
    const drawParcel = (drawX, drawY) => ctx.drawImage(
      definition.image,
      frame * definition.frameW,
      definition.row * definition.frameH,
      definition.frameW,
      definition.frameH,
      drawX,
      drawY,
      definition.frameW,
      definition.frameH,
    );
    drawParcel(x - 2, footY - definition.frameH);
    drawParcel(x + 9, footY - definition.frameH - 13);
  }

  drawPersonalItem(id, centerX, footY, width, height) {
    const image = this.assets.item(id);
    const itemWidth = image.naturalWidth || image.width || 32;
    const itemHeight = image.naturalHeight || image.height || 32;
    const x = centerX + width / 2 - itemWidth - 8;
    const y = footY - height - 3;
    this.ctx.drawImage(image, x, y, itemWidth, itemHeight);
  }

  drawDeskClutter(id, centerX, footY, deskWidth) {
    const hash = stableHash(id);
    const count = id === (this.scene.human_id || "human") ? 1 : 1 + (hash % 2);
    const positions = [-deskWidth / 2 + 7, deskWidth / 2 - 39];
    for (let index = 0; index < count; index += 1) {
      const variant = String.fromCharCode(97 + ((hash >>> (index * 3 + 2)) % 4));
      const image = this.assets.prop(`clutter_${variant}`, 32, 16);
      const width = image.naturalWidth || image.width || 32;
      const height = image.naturalHeight || image.height || 16;
      const jitter = ((hash >>> (index * 5 + 4)) % 5) - 2;
      const x = Math.round(centerX + positions[index] + jitter);
      const yJitter = (hash >>> (index * 4 + 3)) % 4;
      const y = Math.round(footY - 29 - height - yJitter);
      this.ctx.drawImage(image, x, y, width, height);
    }
  }

  updateCat(deltaSeconds) {
    if (!this.cat) return;
    this.cat.nextMove -= deltaSeconds;
    if (!this.cat.moving && this.cat.nextMove <= 0) {
      const tileX = Math.round(this.cat.x / this.tile - 0.5);
      const tileY = Math.round(this.cat.y / this.tile - 1);
      const dx = (Math.floor(Math.random() * 7) - 3) || 2;
      const dy = Math.floor(Math.random() * 5) - 2;
      this.cat.targetX = (Math.max(23, Math.min(36, tileX + dx)) + 0.5) * this.tile;
      this.cat.targetY = (Math.max(6, Math.min(21, tileY + dy)) + 1) * this.tile;
      this.cat.moving = true;
    }
    if (!this.cat.moving) return;
    const dx = this.cat.targetX - this.cat.x;
    const dy = this.cat.targetY - this.cat.y;
    const distance = Math.hypot(dx, dy);
    const step = 24 * deltaSeconds;
    if (distance <= step) {
      this.cat.x = this.cat.targetX;
      this.cat.y = this.cat.targetY;
      this.cat.moving = false;
      this.cat.nextMove = 6 + Math.random() * 8;
      return;
    }
    this.cat.x += (dx / distance) * step;
    this.cat.y += (dy / distance) * step;
  }

  drawCat() {
    const image = this.assets.prop("cat", 32, 32);
    const width = image.naturalWidth || image.width || 32;
    const height = image.naturalHeight || image.height || 32;
    const flipped = this.cat.targetX < this.cat.x;
    this.ctx.save();
    this.ctx.translate(Math.round(this.cat.x), Math.round(this.cat.y));
    drawGroundShadow(this.ctx, 0, -2, 13, 4);
    if (flipped) this.ctx.scale(-1, 1);
    this.ctx.drawImage(image, -width / 2, -height, width, height);
    this.ctx.restore();
  }

  drawWhiteboardText() {
    const board = this.scene.props.whiteboard;
    if (!board) return;
    const x = board.tile[0] * this.tile;
    const y = board.tile[1] * this.tile;
    const width = board.w * this.tile;
    const ctx = this.ctx;
    ctx.save();
    const options = { fontSize: 9, scale: 1, bold: true, color: "#343039" };
    drawPixelText(ctx, "今日の指示", x + 13, y + 8, options);
    this.instructions.forEach((line, index) => {
      let safe = String(line).replaceAll(/\s+/g, " ").slice(0, 22);
      while (safe && measurePixelText(`${index + 1}. ${safe}`, options) > width - 26) safe = safe.slice(0, -1);
      drawPixelText(ctx, `${index + 1}. ${safe}`, x + 13, y + 23 + index * 12, options);
    });
    ctx.restore();
  }

  drawHangingSign() {
    const ctx = this.ctx;
    const x = 32;
    const y = 34;
    const width = 280;
    const height = 42;
    ctx.save();
    ctx.fillStyle = "#31231d";
    for (const chainX of [x + 54, x + width - 54]) {
      for (let chainY = 22; chainY < y; chainY += 5) {
        ctx.fillRect(chainX, chainY, 3, 3);
        ctx.fillRect(chainX + 2, chainY + 3, 3, 3);
      }
    }
    ctx.fillStyle = "#1d120e";
    ctx.fillRect(x + 5, y + 5, width, height);
    ctx.fillStyle = "#4a2d1d";
    ctx.fillRect(x, y, width, height);
    ctx.fillStyle = "#a66f3f";
    ctx.fillRect(x + 3, y + 3, width - 6, height - 6);
    ctx.fillStyle = "#5d3924";
    ctx.fillRect(x + 7, y + 7, width - 14, height - 14);
    ctx.fillStyle = "#d5a063";
    ctx.fillRect(x + 9, y + 9, width - 18, 2);
    drawPixelText(ctx, "ANIMAWORKS PIXEL OFFICE", x + 20, y + 15, {
      fontSize: 8,
      scale: 1,
      bold: true,
      bitmap: false,
      color: "#fff0ca",
      shadow: "#2d1b14",
      shadowX: 2,
      shadowY: 2,
    });
    const definition = this.assets.fxDefinition(this.mode === "night" ? "moon" : "sun");
    ctx.drawImage(
      definition.image,
      0,
      definition.row * definition.frameH,
      definition.frameW,
      definition.frameH,
      x + width - 100,
      y + 9,
      24,
      24,
    );
    drawPixelText(ctx, this.signDate, x + width - 69, y + 15, {
      fontSize: 9,
      scale: 1,
      bold: true,
      bitmap: false,
      color: "#fff0ca",
      shadow: "#2d1b14",
      shadowX: 1,
      shadowY: 1,
    });
    ctx.restore();
  }

  drawLighting() {
    if (this.mode !== "night") return;
    const ctx = this.ctx;
    ctx.save();
    ctx.globalCompositeOperation = "multiply";
    ctx.fillStyle = this.scene.lighting.night.tint;
    ctx.globalAlpha = 0.48;
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    const firstCompany = Object.values(this.scene.zones).find((zone) => zone.kind === "company");
    if (firstCompany) {
      ctx.globalCompositeOperation = "screen";
      ctx.globalAlpha = 0.12;
      ctx.fillStyle = "#ffb35a";
      ctx.fillRect(
        firstCompany.rect[0] * this.tile,
        Math.max(firstCompany.rect[1], firstCompany.rect[3] - 4) * this.tile,
        Math.min(9, firstCompany.rect[2] - firstCompany.rect[0] + 1) * this.tile,
        Math.min(5, firstCompany.rect[3] - firstCompany.rect[1] + 1) * this.tile,
      );
    }
    ctx.restore();
  }

  drawPaletteUnifier() {
    if (this.mode === "night") return;
    const ctx = this.ctx;
    ctx.save();
    ctx.globalAlpha = 0.05;
    ctx.fillStyle = "#ffedd6";
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.restore();
  }
}
