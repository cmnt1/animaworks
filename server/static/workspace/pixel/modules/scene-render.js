import { drawPixelText, measurePixelText } from "./pixel-text.js";

const COLLISION_PADDING = 2;
const BUBBLE_NAME_GAP = 8;

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

function rectanglesOverlap(left, right, padding = COLLISION_PADDING) {
  return left.x < right.x + right.width + padding &&
    left.x + left.width + padding > right.x &&
    left.y < right.y + right.height + padding &&
    left.y + left.height + padding > right.y;
}

function collisionFreeOffset(bounds, placed, candidates, canvasHeight) {
  for (const offset of candidates) {
    const shifted = { ...bounds, y: bounds.y + offset };
    if (shifted.y < 2 || shifted.y + shifted.height > canvasHeight - 2) continue;
    if (!placed.some((other) => rectanglesOverlap(shifted, other))) return offset;
  }
  return candidates.at(-1) || 0;
}

function findCollisionFreePlacement(bounds, placed, candidates, canvasWidth, canvasHeight) {
  for (const candidate of candidates) {
    const shifted = {
      ...bounds,
      x: bounds.x + candidate.x,
      y: bounds.y + candidate.y,
    };
    if (shifted.x < 2 || shifted.x + shifted.width > canvasWidth - 2 ||
        shifted.y < 2 || shifted.y + shifted.height > canvasHeight - 2) continue;
    if (!placed.some((other) => rectanglesOverlap(shifted, other))) return candidate;
  }
  return null;
}

function collisionFreePlacement(bounds, placed, candidates, canvasWidth, canvasHeight) {
  const placement = findCollisionFreePlacement(
    bounds,
    placed,
    candidates,
    canvasWidth,
    canvasHeight,
  );
  if (placement) return placement;
  return candidates.at(-1) || { x: 0, y: 0 };
}

export class SceneRenderer {
  constructor(canvas, scene, assets) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d", { alpha: false });
    this.ctx.imageSmoothingEnabled = false;
    this.scene = scene;
    this.assets = assets;
    this.backgroundMode = Boolean(
      scene.background_mode?.enabled &&
      assets.officeBackground() &&
      scene.background_mode?.slots,
    );
    this.tile = scene.canvas.tile;
    this.mode = "day";
    this.instructions = [];
    this.humanFlash = 0;
    this.signDate = new Intl.DateTimeFormat("ja-JP", {
      month: "2-digit",
      day: "2-digit",
      weekday: "short",
    }).format(new Date());
    const catProp = this.backgroundMode ? null : scene.props.cat;
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
    this.toneCanvas = document.createElement("canvas");
    this.toneCanvas.width = scene.canvas.w;
    this.toneCanvas.height = scene.canvas.h;
    this.backgroundFrameCanvas = document.createElement("canvas");
    this.backgroundFrameCanvas.width = scene.canvas.w;
    this.backgroundFrameCanvas.height = scene.canvas.h;
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
    if (this.backgroundMode) {
      this.drawBackgroundMode(actors, director);
      return;
    }
    this.drawFloor();
    this.drawHumanPlatform();
    this.drawPathChevrons();
    this.drawPlazaGuideLines();
    this.drawWalls();
    const { under, layers } = this.buildFurnitureLayers(timeSeconds, actors);
    under.sort((a, b) => a.y - b.y).forEach((layer) => layer.draw());
    this.drawBottomWall();

    for (const actor of actors.values()) {
      const desk = this.scene.desks[actor.id];
      const deskFootY = desk ? (desk.tile[1] + 2) * this.tile : actor.y;
      layers.push({
        y: actor.isSeated
          ? deskFootY - 1
          : actor.y,
        priority: 0,
        draw: () => actor.draw(ctx),
      });
    }
    if (this.cat) {
      layers.push({
        y: this.cat.y,
        draw: () => this.drawCat(),
      });
    }
    layers.sort((a, b) => (a.y - b.y) || ((a.priority ?? 1) - (b.priority ?? 1)));
    layers.forEach((layer) => layer.draw());

    this.drawStaticLabels();
    this.drawHumanGlass();
    this.drawWhiteboardText();
    this.drawHangingSign();
    director?.draw(ctx);
    const overlayLayouts = [];
    const placedNames = [];
    const overlayActors = [...actors.values()].sort((left, right) =>
      (left.y - right.y) || (left.x - right.x));
    for (const actor of overlayActors) {
      const desk = this.scene.desks[actor.id];
      const footX = desk ? desk.tile[0] * this.tile + this.tile / 2 : actor.x;
      const footY = desk ? (desk.tile[1] + 2) * this.tile : actor.y;
      const namePosition = actor.isSeated ? { x: footX, y: footY - 11 } : {};
      const nameBounds = actor.nameBounds(namePosition);
      const nameOffsetY = collisionFreeOffset(
        nameBounds,
        placedNames,
        [0, 13, -13, 26, -26, 39, -39],
        this.canvas.height,
      );
      placedNames.push({ ...nameBounds, y: nameBounds.y + nameOffsetY });
      overlayLayouts.push({
        actor,
        namePosition,
        nameOffsetY,
      });
    }
    const nameObstaclePadding = BUBBLE_NAME_GAP - COLLISION_PADDING;
    const bubbleNameObstacles = placedNames.map((bounds) => ({
      x: bounds.x - nameObstaclePadding,
      y: bounds.y - nameObstaclePadding,
      width: bounds.width + nameObstaclePadding * 2,
      height: bounds.height + nameObstaclePadding * 2,
    }));
    const placedBubbles = [...this.staticLabelBounds(), ...bubbleNameObstacles];
    for (const [id, desk] of Object.entries(this.scene.desks)) {
      const isHuman = id === (this.scene.human_id || "human");
      const width = isHuman ? 136 : 112;
      const height = isHuman ? 80 : 72;
      const footX = desk.tile[0] * this.tile + this.tile / 2;
      const footY = (desk.tile[1] + 2) * this.tile;
      placedBubbles.push({
        x: footX - width / 2,
        y: footY - height,
        width,
        height,
      });
    }
    const actorBubbleObstacles = overlayActors.map((actor) => {
      const spriteY = actor.spriteY();
      return {
        actor,
        x: actor.x - actor.sprite.frameW / 2,
        y: spriteY - actor.sprite.frameH,
        width: actor.sprite.frameW,
        height: actor.sprite.frameH,
      };
    });
    const bubbleCandidates = [];
    for (const rise of [0, -36, -72, -108, -144, -180]) {
      for (const shift of [0, -100, 100, -200, 200, -300, 300, -400, 400]) {
        bubbleCandidates.push({ x: shift, y: rise });
      }
    }
    for (const layout of overlayLayouts) {
      const { actor } = layout;
      if (!actor.hasFullBubble()) continue;
      const bubbleBounds = actor.bubbleBounds();
      const bubblePlacement = collisionFreePlacement(
        bubbleBounds,
        [
          ...placedBubbles,
          ...actorBubbleObstacles.filter((obstacle) => obstacle.actor !== actor),
        ],
        bubbleCandidates,
        this.canvas.width,
        this.canvas.height,
      );
      placedBubbles.push({
        ...bubbleBounds,
        x: bubbleBounds.x + bubblePlacement.x,
        y: bubbleBounds.y + bubblePlacement.y,
      });
      layout.bubbleOffsetX = bubblePlacement.x;
      layout.bubbleOffsetY = bubblePlacement.y;
    }
    for (const layout of overlayLayouts) {
      layout.actor.drawStatusOverlay(ctx, layout);
    }
    for (const layout of overlayLayouts) {
      layout.actor.drawNameOverlay(ctx, layout);
    }
    this.drawLighting();
    this.drawPaletteUnifier();
    this.drawVignette();
    this.applyUnifiedTone();
  }

  drawBackgroundMode(actors, director) {
    const { ctx } = this;
    const background = this.assets.officeBackground();
    ctx.drawImage(background, 0, 0, this.canvas.width, this.canvas.height);
    if (this.mode === "night") this.drawBackgroundNight();
    this.drawWhiteboardText();
    const backgroundFrameCtx = this.backgroundFrameCanvas.getContext("2d");
    backgroundFrameCtx.imageSmoothingEnabled = false;
    backgroundFrameCtx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    backgroundFrameCtx.drawImage(this.canvas, 0, 0);

    const allActors = [...actors.values()];
    const seated = allActors
      .filter((actor) => actor.isSeated)
      .sort((left, right) => (left.y - right.y) || (left.x - right.x));
    const walking = allActors
      .filter((actor) => !actor.isSeated)
      .sort((left, right) => (left.y - right.y) || (left.x - right.x));
    const seatedLayers = seated.flatMap((actor) => {
      const rect = this.deskOcclusionRect(actor);
      const depth = rect ? rect[1] + rect[3] : actor.y;
      return [
        {
          depth,
          priority: 0,
          x: actor.x,
          draw: () => this.drawSeatedBackgroundActor(actor),
        },
        {
          depth,
          priority: 1,
          x: actor.x,
          draw: () => this.drawDeskOcclusion(actor),
        },
        {
          depth: depth + 2,
          priority: 0,
          x: actor.x,
          draw: () => actor.drawName(this.ctx, actor.backgroundNamePosition || {}),
        },
      ];
    });
    seatedLayers
      .sort((left, right) =>
        (left.depth - right.depth) ||
        (left.priority - right.priority) ||
        (left.x - right.x))
      .forEach((layer) => layer.draw());
    walking.forEach((actor) => actor.draw(ctx));
    director?.draw(ctx);
    this.drawBackgroundOverlays(allActors);
    this.drawPaletteUnifier();
    this.drawVignette();
    this.applyUnifiedTone();
  }

  deskOcclusionRect(actor) {
    return actor.backgroundSlot?.desk_rect || null;
  }

  drawDeskOcclusion(actor) {
    const rect = this.deskOcclusionRect(actor);
    if (!rect) return;
    // desk_rect は机そのもの。front_rects は机より上に飛び出す前景物
    // (モニタ・卓上ライト等) を個別に指定するためのもので、指定した矩形だけを
    // 背景から描き戻すためキャラの周囲に不要な切り取り線ができない。
    const rects = [rect, ...(actor.backgroundSlot?.front_rects || [])];
    for (const [x, y, width, height] of rects) {
      this.ctx.save();
      this.ctx.beginPath();
      this.ctx.rect(x, y, width, height);
      this.ctx.clip();
      this.ctx.drawImage(
        this.backgroundFrameCanvas,
        x,
        y,
        width,
        height,
        x,
        y,
        width,
        height,
      );
      this.ctx.restore();
    }
  }

  drawSeatedBackgroundActor(actor) {
    // 着席キャラは机・PCより先に描き、そのあとで机の領域を背景から描き戻す
    // (drawDeskOcclusion)。机とPCが手前・キャラが奥、という重なりになる。
    actor.draw(this.ctx);
  }

  drawBackgroundNight() {
    const ctx = this.ctx;
    ctx.save();
    ctx.globalCompositeOperation = "multiply";
    ctx.globalAlpha = 0.46;
    ctx.fillStyle = this.scene.lighting?.night?.tint || "#2a2a4a";
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.restore();
  }

  drawBackgroundOverlays(allActors) {
    const layouts = [];
    const placedNames = [];
    const overlayActors = [...allActors].sort((left, right) =>
      (left.y - right.y) || (left.x - right.x));
    for (const actor of overlayActors) {
      let namePosition = actor.isSeated && actor.backgroundNamePosition
        ? actor.backgroundNamePosition
        : {};
      const door = this.scene.background_mode?.slots?.door;
      const nearDoor = !actor.isSeated && door &&
        Math.abs(actor.x - door.x) <= 112 &&
        actor.y >= door.y - 150;
      if (nearDoor) {
        const headTop = actor.headTop(actor.y);
        namePosition = {
          x: actor.x,
          y: actor.hasFullBubble() ? actor.bubbleBounds().y - 19 : headTop - 14,
        };
      }
      const nameBounds = actor.nameBounds(namePosition);
      const nameOffsetY = actor.isSeated ? 0 : collisionFreeOffset(
        nameBounds,
        placedNames,
        [0, 13, -13, 26, -26, 39, -39],
        this.canvas.height,
      );
      placedNames.push({ ...nameBounds, y: nameBounds.y + nameOffsetY });
      layouts.push({ actor, namePosition, nameOffsetY });
    }

    const nameObstaclePadding = BUBBLE_NAME_GAP - COLLISION_PADDING;
    const nameObstacles = placedNames.map((bounds) => ({
      x: bounds.x - nameObstaclePadding,
      y: bounds.y - nameObstaclePadding,
      width: bounds.width + nameObstaclePadding * 2,
      height: bounds.height + nameObstaclePadding * 2,
    }));
    const placedBubbles = [];
    const actorObstacles = overlayActors.map((actor) => {
      const spriteY = actor.spriteY();
      const top = spriteY - actor.sprite.frameH;
      const visibleBottom = actor.isSeated && actor.backgroundSlot?.desk_rect
        ? actor.backgroundSlot.desk_rect[1]
        : spriteY;
      return {
        actor,
        x: actor.x - actor.sprite.frameW / 2,
        y: top,
        width: actor.sprite.frameW,
        height: Math.max(0, visibleBottom - top),
      };
    });
    // Keep the tail on its owner unless the bubble would cover a character in
    // the row behind it. Candidates are ordered by total displacement (with
    // horizontal moves penalized) so a bubble prefers rising slightly above
    // its owner over flying sideways to another character's desk.
    const candidates = [{ x: 0, y: 0 }];
    for (const rise of [0, -20, -27, -36, -52, -72, -88, -108]) {
      for (const shift of [
        0, -16, 16, -32, 32, -48, 48, -64, 64, -80, 80,
        -96, 96, -128, 128, -160, 160, -200, 200,
        -240, 240, -300, 300, -360, 360, -400, 400,
      ]) {
        if (rise === 0 && shift === 0) continue;
        candidates.push({ x: shift, y: rise });
      }
    }
    candidates.sort((left, right) =>
      (Math.abs(left.x) * 1.6 + Math.abs(left.y)) -
      (Math.abs(right.x) * 1.6 + Math.abs(right.y)));
    const nearbyCandidates = candidates.filter((candidate) =>
      Math.abs(candidate.x) * 1.6 + Math.abs(candidate.y) <= 130);
    for (const layout of layouts) {
      const { actor } = layout;
      if (!actor.hasFullBubble()) continue;
      const bounds = actor.bubbleBounds();
      const behindActorObstacles = actorObstacles.filter((obstacle) =>
        obstacle.actor !== actor && obstacle.actor.y < actor.y);
      // Stay near the owner: first try nearby spots that cover nobody, then
      // nearby spots that may cover a back-row character, and only then move
      // far away as a last resort.
      const placement = findCollisionFreePlacement(
        bounds,
        [
          ...nameObstacles,
          ...placedBubbles,
          ...behindActorObstacles,
        ],
        nearbyCandidates,
        this.canvas.width,
        this.canvas.height,
      ) || findCollisionFreePlacement(
        bounds,
        [...nameObstacles, ...placedBubbles],
        nearbyCandidates,
        this.canvas.width,
        this.canvas.height,
      ) || findCollisionFreePlacement(
        bounds,
        [...nameObstacles, ...placedBubbles],
        candidates,
        this.canvas.width,
        this.canvas.height,
      ) || { x: 0, y: 0 };
      placedBubbles.push({
        ...bounds,
        x: bounds.x + placement.x,
        y: bounds.y + placement.y,
      });
      layout.bubbleOffsetX = placement.x;
      layout.bubbleOffsetY = placement.y;
    }
    layouts.forEach((layout) => layout.actor.drawStatusOverlay(this.ctx, layout));
    layouts.forEach((layout) => {
      if (!layout.actor.isSeated) {
        layout.actor.drawName(this.ctx, {
          ...layout.namePosition,
          offsetY: layout.nameOffsetY || 0,
        });
      }
      layout.actor.drawStatusDot(this.ctx, {
        ...layout.namePosition,
        offsetY: layout.nameOffsetY || 0,
      });
    });
  }

  drawFloor() {
    const { ctx, tile } = this;
    ctx.fillStyle = "#493936";
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.save();
    ctx.fillStyle = "#251c20";
    ctx.globalAlpha = 0.28;
    for (let row = 4; row < Math.ceil(this.canvas.height / tile); row += 1) {
      const y = row * tile;
      ctx.fillRect(0, y, this.canvas.width, 1);
      const offset = row % 2 ? tile * 1.5 : 0;
      for (let x = offset; x < this.canvas.width; x += tile * 3) {
        ctx.fillRect(Math.round(x), y, 1, tile);
      }
    }
    ctx.restore();
    this.drawExteriorDetails();

    const floorColors = {
      wood_warm: ["#dcbf8b", "#d4b37d"],
      wood_cool: ["#c4b8a2", "#b9ab94"],
      carpet_blue: ["#8a9aae", "#8493a5"],
      mat: ["#aa7f69", "#9d725e"],
      stone_warm: ["#cbb58f", "#c2aa83"],
      plaza: ["#dcc9a5", "#d3bc94"],
    };
    const cells = new Map();
    for (const [name, zone] of Object.entries(this.scene.zones)) {
      if (zone.kind === "entrance") continue;
      const floorName = zone.floor;
      const group = name;
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
        if (cell.floorName === "stone_warm" || cell.floorName === "plaza") {
          ctx.fillStyle = "#705b451f";
          ctx.fillRect(px, py, 1, tile);
          ctx.fillRect(px, py + tile - 1, tile, 1);
        }
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
      ctx.save();
      ctx.fillStyle = "#3b2a25";
      ctx.globalAlpha = 0.2;
      if (side === "left") ctx.fillRect(px, py, 1, tile);
      else if (side === "right") ctx.fillRect(px + tile - 1, py, 1, tile);
      else if (side === "top") ctx.fillRect(px, py, tile, 1);
      else ctx.fillRect(px, py + tile - 1, tile, 1);
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

    this.drawCorridorPaving();
    this.drawFloorAmbient();
  }

  drawCorridorPaving() {
    const path = this.scene.zones.path;
    const entrance = this.scene.zones.entrance;
    if (!path) return;
    const [x1, y1, x2, pathBottom] = path.rect;
    const y2 = Math.min(pathBottom, (entrance?.rect?.[1] ?? pathBottom + 1) + 1);
    const ctx = this.ctx;
    ctx.save();
    for (let tileY = y1; tileY <= y2; tileY += 1) {
      for (let tileX = x1; tileX <= x2; tileX += 1) {
        ctx.globalAlpha = 0.09;
        ctx.fillStyle = (tileX + tileY) % 2 ? "#f1ddba" : "#8f7965";
        ctx.fillRect(
          tileX * this.tile + 1,
          tileY * this.tile + 1,
          this.tile - 2,
          this.tile - 2,
        );
      }
    }
    ctx.restore();
  }

  drawFloorAmbient() {
    const ctx = this.ctx;
    const top = this.tile * 4;
    const bottom = this.canvas.height - this.tile * 2;
    const gradient = ctx.createLinearGradient(0, top, 0, bottom);
    gradient.addColorStop(0, "rgba(255,255,255,0.025)");
    gradient.addColorStop(0.55, "rgba(255,255,255,0)");
    gradient.addColorStop(1, "rgba(0,0,0,0.035)");
    ctx.save();
    ctx.fillStyle = gradient;
    ctx.fillRect(0, top, this.canvas.width, bottom - top);
    ctx.restore();
  }

  drawExteriorDetails() {
    const { ctx, tile } = this;
    const windows = [
      [4, 20], [11, 21], [16, 20],
      [22, 20], [28, 20], [35, 21],
    ];
    ctx.save();
    for (const [tileX, tileY] of windows) {
      const x = tileX * tile + 4;
      const y = tileY * tile + 5;
      ctx.fillStyle = "#21191d";
      ctx.globalAlpha = 0.68;
      ctx.fillRect(x - 3, y - 3, 30, 24);
      ctx.fillStyle = "#8f7059";
      ctx.fillRect(x - 1, y - 1, 26, 20);
      ctx.fillStyle = "#344b58";
      ctx.fillRect(x + 2, y + 2, 20, 14);
      ctx.fillStyle = "#9bb8bd";
      ctx.globalAlpha = 0.34;
      ctx.fillRect(x + 4, y + 4, 7, 2);
      ctx.fillRect(x + 12, y + 6, 6, 2);
      ctx.globalAlpha = 0.5;
      ctx.fillStyle = "#1d171a";
      ctx.fillRect(x + 11, y + 2, 2, 14);
    }

    for (const tileX of [17, 23]) {
      const x = tileX * tile + (tileX === 17 ? 23 : 6);
      const top = 19 * tile + 7;
      const bottom = 24 * tile;
      ctx.globalAlpha = 0.62;
      ctx.fillStyle = "#21191d";
      ctx.fillRect(x - 2, top, 6, bottom - top);
      ctx.fillRect(tileX === 17 ? x - 12 : x, top - 2, 14, 6);
      ctx.fillStyle = "#9a6b4c";
      ctx.fillRect(x, top + 1, 2, bottom - top - 2);
      ctx.fillRect(tileX === 17 ? x - 10 : x + 2, top, 10, 2);
      ctx.fillStyle = "#bb8a61";
      ctx.fillRect(x, top + 8, 2, 3);
      ctx.fillRect(x, top + 55, 2, 3);
    }

    for (const [tileX, tileY] of [[7, 22], [31, 22]]) {
      const x = tileX * tile;
      const y = tileY * tile + 4;
      ctx.globalAlpha = 0.56;
      ctx.fillStyle = "#21191d";
      ctx.fillRect(x, y, 36, 20);
      ctx.fillStyle = "#72594c";
      ctx.fillRect(x + 2, y + 2, 32, 16);
      ctx.fillStyle = "#2d2426";
      for (let line = 0; line < 4; line += 1) {
        ctx.fillRect(x + 6, y + 5 + line * 3, 24, 1);
      }
    }
    ctx.restore();
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

  drawPlazaGuideLines() {
    const plaza = this.scene.zones.plaza;
    const mat = this.scene.props.welcome_mat;
    if (!plaza || !mat) return;
    const centerX = (mat.tile[0] + mat.w / 2) * this.tile;
    const top = plaza.rect[1] * this.tile;
    const bottom = (plaza.rect[3] + 1) * this.tile;
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = "#fff0c8";
    ctx.globalAlpha = 0.38;
    ctx.fillRect(centerX - 44, top, 2, bottom - top);
    ctx.fillRect(centerX + 42, top, 2, bottom - top);
    ctx.globalAlpha = 0.22;
    for (let y = top + 12; y < bottom; y += 24) {
      ctx.fillRect(centerX - 41, y, 82, 2);
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

  drawBottomWall() {
    const { ctx, tile } = this;
    const wall = this.assets.wallBottom();
    const wallHeight = wall?.naturalHeight || wall?.height || tile * 2;
    const wallY = this.canvas.height - wallHeight;
    if (wall) {
      ctx.drawImage(wall, 0, wallY, this.canvas.width, wallHeight);
    } else {
      ctx.fillStyle = "#4a3027";
      ctx.fillRect(0, wallY, this.canvas.width, wallHeight);
      ctx.fillStyle = "#b47a4e";
      ctx.fillRect(0, wallY, this.canvas.width, 2);
    }

    const entrance = this.scene.zones.entrance?.rect;
    const door = this.scene.props.door_frame || {
      tile: [
        entrance ? Math.floor((entrance[0] + entrance[2] - 5) / 2) : 17,
        Math.floor(this.canvas.height / tile) - 3,
      ],
      w: 6,
      h: 4,
      bottom_inset: 64,
    };
    const image = this.assets.prop("door_frame", door.w * tile, door.h * tile);
    const width = image.naturalWidth || image.width || door.w * tile;
    const height = image.naturalHeight || image.height || door.h * tile;
    const bottomInset = door.bottom_inset ?? 64;
    const x = door.tile[0] * tile;
    const y = this.canvas.height - height - bottomInset;
    const bottom = y + height;
    ctx.save();
    ctx.fillStyle = "#171015";
    ctx.globalAlpha = 0.32;
    ctx.fillRect(x + 8, bottom - 3, width - 16, 3);
    ctx.restore();
    ctx.drawImage(
      image,
      x,
      y,
      width,
      height,
    );
    ctx.fillStyle = "#3b241c";
    ctx.fillRect(x + 10, bottom - 1, width - 20, 1);
  }

  drawStaticLabels() {
    const { ctx, tile } = this;
    for (const zone of Object.values(this.scene.zones)) {
      if (!zone.label) continue;
      const [x1, y1, x2] = zone.rect;
      if (y1 < 4) continue;
      ctx.save();
      const textOptions = { fontSize: 4, scale: 2, bold: true };
      const width = measurePixelText(zone.label, textOptions) + 18;
      const zoneLeft = x1 * tile;
      const zoneRight = (x2 + 1) * tile;
      const x = Math.min(zoneRight - width - 8, zoneLeft + 40);
      const y = zone.kind === "entrance" ? y1 * tile - 54 : y1 * tile + 7;
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

  staticLabelBounds() {
    const bounds = [];
    const { tile } = this;
    for (const zone of Object.values(this.scene.zones)) {
      if (!zone.label) continue;
      const [x1, y1, x2] = zone.rect;
      if (y1 < 4) continue;
      const textOptions = { fontSize: 4, scale: 2, bold: true };
      const width = measurePixelText(zone.label, textOptions) + 18;
      const zoneLeft = x1 * tile;
      const zoneRight = (x2 + 1) * tile;
      const x = Math.min(zoneRight - width - 8, zoneLeft + 40);
      const y = zone.kind === "entrance" ? y1 * tile - 54 : y1 * tile + 7;
      bounds.push({ x: x - 2, y: y - 2, width: width + 4, height: 20 });
    }
    return bounds;
  }

  buildFurnitureLayers(timeSeconds, actors) {
    const { tile, scene, assets } = this;
    const layers = [];
    const under = [];

    for (const [id, desk] of Object.entries(scene.desks)) {
      const isHuman = id === (scene.human_id || "human");
      const deskAsset = isHuman ? "desk_taka" : "desk";
      const deskImage = assets.prop(deskAsset, isHuman ? 136 : 112, isHuman ? 80 : 72);
      const width = deskImage.naturalWidth || deskImage.width || (isHuman ? 136 : 112);
      const height = deskImage.naturalHeight || deskImage.height || (isHuman ? 80 : 72);
      const footX = desk.tile[0] * tile + tile / 2;
      const footY = (desk.tile[1] + 2) * tile;
      const actor = actors.get(id);
      if (actor?.isSeated) {
        layers.push({
          y: footY - 2,
          priority: -1,
          draw: () => {
            const chair = assets.prop("chair", 32, 40);
            // The seated poses are wider than the opaque chair pixels; 48px keeps
            // the requested ~44px scale while exposing a 2px armrest cue per side.
            const chairWidth = 48;
            const sourceX = 3;
            const sourceY = 1;
            const sourceWidth = 26;
            const sourceHeight = 38;
            const chairHeight = Math.round(chairWidth * sourceHeight / sourceWidth);
            drawGroundShadow(
              this.ctx,
              Math.round(actor.seatPosition.x),
              Math.round(actor.seatPosition.y - 2),
              18,
              5,
            );
            this.ctx.drawImage(
              chair,
              sourceX,
              sourceY,
              sourceWidth,
              sourceHeight,
              Math.round(actor.seatPosition.x - chairWidth / 2),
              Math.round(actor.seatPosition.y - chairHeight + 9),
              chairWidth,
              chairHeight,
            );
          },
        });
      }
      layers.push({
        y: footY,
        draw: () => {
          const ctx = this.ctx;
          if (isHuman && this.humanFlash > 0) {
            ctx.save();
            ctx.globalAlpha = 0.35 + Math.sin(timeSeconds * 14) * 0.18;
            ctx.fillStyle = "#ffe879";
            ctx.fillRect(footX - width / 2 - 8, footY - height - 8, width + 16, height + 16);
            ctx.restore();
          }
          drawGroundShadow(ctx, footX, footY - 3, width * 0.36, 7);
          ctx.drawImage(deskImage, footX - width / 2, footY - height, width, height);
          this.drawPersonalItem(desk.item || id, footX, footY, width, height);
          this.drawDeskClutter(id, footX, footY, width);
          this.drawDeskLamp(id, footX, footY, width);
        },
      });
    }

    const desksByRow = new Map();
    for (const [id, desk] of Object.entries(scene.desks)) {
      if (id === (scene.human_id || "human")) continue;
      const key = `${desk.company || "default"}:${desk.tile[1]}`;
      if (!desksByRow.has(key)) desksByRow.set(key, []);
      desksByRow.get(key).push(desk);
    }
    for (const row of desksByRow.values()) {
      row.sort((left, right) => left.tile[0] - right.tile[0]);
      for (let index = 0; index < row.length - 1; index += 1) {
        const left = row[index];
        const right = row[index + 1];
        if (right.tile[0] - left.tile[0] > 5) continue;
        const x = ((left.tile[0] + right.tile[0] + 1) / 2) * tile;
        const footY = (left.tile[1] + 2) * tile;
        layers.push({
          y: footY - 1,
          priority: -0.5,
          draw: () => this.drawDeskPartition(x, footY),
        });
      }
    }

    for (const [name, prop] of Object.entries(scene.props)) {
      if (name === "plants" || name === "cat" ||
          name === "door" || name === "door_frame" || name === "sign_stand") continue;
      const width = prop.w * tile;
      const height = prop.h * tile;
      const x = prop.tile[0] * tile;
      const footY = (prop.tile[1] + prop.h) * tile;
      const assetName = prop.sprite || (prop.kind === "meeting" ? "meeting_table" : name);
      const target = prop.under ? under : layers;
      target.push({
        y: footY,
        draw: () => {
          if (prop.decor) {
            this.drawSceneDecoration(prop.decor, x, footY, width, height, timeSeconds);
            return;
          }
          if (name === "parcel_door" && !assets.images.has("scene.props.parcel_stack")) {
            this.drawParcelStack(x, footY, timeSeconds);
            return;
          }
          const image = assets.prop(assetName, width, height);
          const drawWidth = image.naturalWidth || image.width || width;
          const drawHeight = image.naturalHeight || image.height || height;
          if (!prop.under && !prop.wall) {
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

  drawDeskPartition(centerX, footY) {
    const ctx = this.ctx;
    const x = Math.round(centerX - 6);
    const y = Math.round(footY - 43);
    ctx.save();
    drawGroundShadow(ctx, centerX, footY - 2, 8, 3);
    ctx.fillStyle = "#4d3328";
    ctx.fillRect(x, y, 12, 38);
    ctx.fillStyle = "#c89461";
    ctx.fillRect(x + 2, y + 3, 8, 29);
    ctx.fillStyle = "#efd2a0";
    ctx.fillRect(x + 3, y + 4, 6, 26);
    ctx.fillStyle = "#2d211d";
    ctx.fillRect(x - 1, y, 14, 3);
    ctx.fillRect(x + 1, y + 35, 3, 7);
    ctx.fillRect(x + 8, y + 35, 3, 7);
    ctx.restore();
  }

  drawSceneDecoration(type, x, footY, width, height, timeSeconds) {
    const ctx = this.ctx;
    ctx.save();
    if (type === "wall_clock") {
      const centerX = Math.round(x + width / 2);
      const centerY = Math.round(footY - height / 2);
      ctx.fillStyle = "#3d281f";
      ctx.fillRect(centerX - 12, centerY - 12, 24, 24);
      ctx.fillStyle = "#d7ad72";
      ctx.fillRect(centerX - 9, centerY - 9, 18, 18);
      ctx.fillStyle = "#fff0ca";
      ctx.fillRect(centerX - 7, centerY - 7, 14, 14);
      ctx.fillStyle = "#593928";
      ctx.fillRect(centerX - 1, centerY - 6, 2, 7);
      ctx.fillRect(centerX, centerY, 6, 2);
      for (const [dx, dy] of [[0, -8], [8, 0], [0, 8], [-8, 0]]) {
        ctx.fillRect(centerX + dx - 1, centerY + dy - 1, 2, 2);
      }
    } else if (type === "wall_shelf") {
      const shelfY = Math.round(footY - 10);
      ctx.fillStyle = "#39251d";
      ctx.fillRect(x + 1, shelfY, width - 2, 5);
      ctx.fillStyle = "#bd8050";
      ctx.fillRect(x + 3, shelfY + 1, width - 6, 2);
      const colors = ["#8a4c4f", "#52718b", "#bf8b45", "#66825c"];
      for (let index = 0; index < 7; index += 1) {
        const bookHeight = 8 + (index % 3) * 3;
        ctx.fillStyle = colors[index % colors.length];
        ctx.fillRect(x + 5 + index * 7, shelfY - bookHeight, 5, bookHeight);
      }
      ctx.fillStyle = "#4a3025";
      ctx.fillRect(x + 7, shelfY + 5, 3, 5);
      ctx.fillRect(x + width - 10, shelfY + 5, 3, 5);
    } else if (type === "stand_lamp") {
      const centerX = Math.round(x + width / 2);
      drawGroundShadow(ctx, centerX, footY - 2, 13, 4);
      ctx.fillStyle = "#4b3228";
      ctx.fillRect(centerX - 8, footY - 7, 16, 5);
      ctx.fillRect(centerX - 2, footY - 47, 4, 41);
      ctx.fillStyle = "#d7a155";
      ctx.fillRect(centerX - 11, footY - 52, 22, 5);
      ctx.fillStyle = "#f2d293";
      ctx.fillRect(centerX - 8, footY - 60, 16, 8);
      ctx.fillStyle = Math.floor(timeSeconds * 2) % 2 ? "#ffe5a5" : "#f6ce7e";
      ctx.fillRect(centerX - 5, footY - 57, 10, 5);
    } else if (type === "guide_lamp") {
      const centerX = Math.round(x + width / 2);
      drawGroundShadow(ctx, centerX, footY - 2, 8, 3);
      ctx.fillStyle = "#3a2f33";
      ctx.fillRect(centerX - 5, footY - 5, 10, 4);
      ctx.fillRect(centerX - 1, footY - 22, 3, 18);
      ctx.fillStyle = "#b97b4b";
      ctx.fillRect(centerX - 6, footY - 27, 12, 6);
      ctx.fillStyle = "#ffe1a0";
      ctx.fillRect(centerX - 3, footY - 25, 6, 3);
    } else if (type === "guide_sign") {
      const centerX = Math.round(x + width / 2);
      drawGroundShadow(ctx, centerX, footY - 2, 9, 3);
      ctx.fillStyle = "#3a2f33";
      ctx.fillRect(centerX - 2, footY - 19, 4, 17);
      ctx.fillStyle = "#5b3928";
      ctx.fillRect(centerX - 13, footY - 28, 26, 11);
      ctx.fillStyle = "#d6aa6e";
      ctx.fillRect(centerX - 11, footY - 26, 22, 7);
      ctx.fillStyle = "#624331";
      const direction = Math.round(x / this.tile) % 2 ? -1 : 1;
      ctx.fillRect(centerX - 5, footY - 24, 10, 2);
      ctx.fillRect(centerX + direction * 4, footY - 26, 2, 6);
    }
    ctx.restore();
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
    const tabletopLeft = centerX - width / 2 + 4;
    const seatingBoundary = centerX - 8;
    const x = Math.min(tabletopLeft, seatingBoundary - itemWidth);
    const y = footY - height - 3;
    this.ctx.drawImage(image, x, y, itemWidth, itemHeight);
  }

  drawDeskClutter(id, centerX, footY, deskWidth) {
    const hash = stableHash(id);
    const count = id === (this.scene.human_id || "human") ? 1 : 1 + (hash % 2);
    const positions = [-deskWidth / 2 + 3, -deskWidth / 2 + 15];
    for (let index = 0; index < count; index += 1) {
      const variant = String.fromCharCode(97 + ((hash >>> (index * 3 + 2)) % 4));
      const image = this.assets.prop(`clutter_${variant}`, 32, 16);
      const width = image.naturalWidth || image.width || 32;
      const height = image.naturalHeight || image.height || 16;
      const jitter = ((hash >>> (index * 5 + 4)) % 5) - 2;
      const seatingBoundary = centerX - 8;
      const x = Math.round(Math.min(
        centerX + positions[index] + jitter,
        seatingBoundary - width,
      ));
      const yJitter = (hash >>> (index * 4 + 3)) % 4;
      const y = Math.round(footY - 29 - height - yJitter);
      this.ctx.drawImage(image, x, y, width, height);
    }
  }

  drawDeskLamp(id, centerX, footY, deskWidth) {
    const hash = stableHash(`lamp:${id}`);
    if (hash % 3 === 0) return;
    const ctx = this.ctx;
    const center = Math.round(Math.min(centerX - 18, centerX + deskWidth / 2 - 18));
    const baseY = Math.round(footY - 29);
    ctx.save();
    ctx.globalAlpha = 0.18;
    ctx.fillStyle = "#1b1218";
    ctx.beginPath();
    ctx.ellipse(center, baseY, 7, 2, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.fillStyle = "#4b3027";
    ctx.fillRect(center - 6, baseY - 3, 12, 3);
    ctx.fillRect(center - 1, baseY - 14, 3, 12);
    ctx.fillStyle = hash % 2 ? "#d28a55" : "#66869a";
    ctx.fillRect(center - 7, baseY - 18, 14, 5);
    ctx.fillStyle = "#ffe2a0";
    ctx.fillRect(center - 4, baseY - 15, 8, 2);
    ctx.restore();
  }

  updateCat(deltaSeconds) {
    if (!this.cat) return;
    this.cat.nextMove -= deltaSeconds;
    if (!this.cat.moving && this.cat.nextMove <= 0) {
      const tileX = Math.round(this.cat.x / this.tile - 0.5);
      const tileY = Math.round(this.cat.y / this.tile - 1);
      const dx = (Math.floor(Math.random() * 7) - 3) || 2;
      const dy = Math.floor(Math.random() * 5) - 2;
      const companyZones = Object.values(this.scene.zones).filter((zone) => zone.kind === "company");
      const zone = companyZones.at(-1);
      const minX = zone ? zone.rect[0] + 1 : 1;
      const maxX = zone ? zone.rect[2] - 1 : Math.floor(this.canvas.width / this.tile) - 2;
      const minY = zone ? zone.rect[1] + 2 : 6;
      const maxY = zone ? zone.rect[3] - 1 : Math.floor(this.canvas.height / this.tile) - 4;
      this.cat.targetX = (Math.max(minX, Math.min(maxX, tileX + dx)) + 0.5) * this.tile;
      this.cat.targetY = (Math.max(minY, Math.min(maxY, tileY + dy)) + 1) * this.tile;
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
    const backgroundBoard = this.scene.background_mode?.slots?.whiteboard;
    const board = backgroundBoard || this.scene.props.whiteboard;
    if (!board) return;
    const x = backgroundBoard ? board.x : board.tile[0] * this.tile;
    const y = backgroundBoard ? board.y : board.tile[1] * this.tile;
    const width = backgroundBoard ? board.w : board.w * this.tile;
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
    if (this.backgroundMode) return;
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

  applyUnifiedTone() {
    const ctx = this.ctx;
    if (!("filter" in ctx)) return;
    const toneCtx = this.toneCanvas.getContext("2d");
    toneCtx.imageSmoothingEnabled = false;
    toneCtx.clearRect(0, 0, this.toneCanvas.width, this.toneCanvas.height);
    toneCtx.drawImage(this.canvas, 0, 0);
    ctx.save();
    ctx.imageSmoothingEnabled = false;
    ctx.filter = "saturate(1.03) contrast(1.03)";
    ctx.drawImage(this.toneCanvas, 0, 0);
    ctx.restore();
  }

  drawVignette() {
    const ctx = this.ctx;
    const width = this.canvas.width;
    const height = this.canvas.height;
    ctx.save();
    ctx.translate(width / 2, height / 2);
    ctx.scale(1, height / width);
    const radius = width * 0.64;
    const gradient = ctx.createRadialGradient(0, 0, radius * 0.62, 0, 0, radius);
    gradient.addColorStop(0, "rgba(0,0,0,0)");
    gradient.addColorStop(0.82, "rgba(0,0,0,0.015)");
    gradient.addColorStop(1, "rgba(0,0,0,0.07)");
    ctx.fillStyle = gradient;
    ctx.fillRect(-width / 2, -width / 2, width, width);
    ctx.restore();
    ctx.save();
    ctx.globalAlpha = 0.08;
    ctx.strokeStyle = "#21171a";
    ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
    ctx.restore();
  }
}
