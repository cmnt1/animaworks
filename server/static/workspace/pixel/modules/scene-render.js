import { drawPixelText, measurePixelText } from "./pixel-text.js";
import { WORK_KINDS } from "./actors.js";

const COLLISION_PADDING = 2;
const DESK_PROPS = [
  ["prop_mug", 16, 16],
  ["prop_plant", 20, 24],
  ["prop_documents", 20, 16],
  ["prop_papers_stack", 20, 12],
  ["prop_pen_stand", 12, 20],
  ["prop_books", 22, 16],
  ["prop_book_open", 24, 16],
  ["prop_binder", 20, 20],
  ["prop_sticky_notes", 14, 10],
  ["prop_photo_frame", 16, 20],
  ["prop_tissue_box", 20, 14],
  ["prop_headphones", 22, 16],
  ["prop_water_bottle", 10, 22],
  ["prop_figurine", 12, 20],
  ["prop_mug_red", 16, 16],
  ["prop_mug_green", 16, 16],
];

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

export class SceneRenderer {
  constructor(canvas, scene, assets) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d", { alpha: false });
    this.ctx.imageSmoothingEnabled = false;
    this.scene = scene;
    this.assets = assets;
    this.backdrop = assets.officeBackground();
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
    this.toneCanvas = document.createElement("canvas");
    this.toneCanvas.width = scene.canvas.w;
    this.toneCanvas.height = scene.canvas.h;
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
    if (this.backdrop) {
      ctx.drawImage(this.backdrop, 0, 0, this.canvas.width, this.canvas.height);
    } else {
      this.drawFloor();
      this.drawPathChevrons();
      this.drawPlazaGuideLines();
      this.drawWalls();
    }
    const { under, layers } = this.buildFurnitureLayers(timeSeconds, actors);
    under.sort((a, b) => a.y - b.y).forEach((layer) => layer.draw());
    if (!this.backdrop) this.drawBottomWall();

    const drawnActors = new Set();
    for (const actor of actors.values()) {
      const desk = this.scene.desks[actor.id];
      const deskFootY = desk ? (desk.tile[1] + 2) * this.tile : actor.y;
      layers.push({
        y: actor.isSeated
          ? deskFootY - 1
          : actor.y,
        priority: 0,
        draw: () => {
          if (actor.draw(ctx)) drawnActors.add(actor.id);
        },
      });
    }
    if (this.cat) {
      layers.push({
        y: this.cat.y,
        draw: () => this.drawCat(),
      });
    }
    layers.push(...(director?.customerLayers(ctx) || []));
    layers.sort((a, b) => (a.y - b.y) || ((a.priority ?? 1) - (b.priority ?? 1)));
    layers.forEach((layer) => layer.draw());

    this.drawStaticLabels();
    this.drawWhiteboardText();
    this.drawFixtureText();
    this.drawHangingSign();
    director?.draw(ctx);
    const overlayLayouts = [];
    const placedNames = [];
    const overlayActors = [...actors.values()]
      .filter((actor) => drawnActors.has(actor.id))
      .sort((left, right) => (left.y - right.y) || (left.x - right.x));
    for (const actor of overlayActors) {
      const desk = this.scene.desks[actor.id];
      const footX = desk ? desk.tile[0] * this.tile + this.tile / 2 : actor.x;
      const footY = desk ? (desk.tile[1] + 2) * this.tile : actor.y;
      const namePosition = actor.isSeated ? { x: footX, y: footY - 11 } : {};
      const nameBounds = actor.nameBounds(namePosition);
      const nameOffsetY = collisionFreeOffset(
        nameBounds,
        placedNames,
        [0, 15, -15, 30, -30, 45, -45],
        this.canvas.height,
      );
      placedNames.push({ ...nameBounds, y: nameBounds.y + nameOffsetY });
      overlayLayouts.push({
        actor,
        namePosition,
        nameOffsetY,
      });
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
    this.drawWorkKindLegend();
  }

  drawFloor() {
    const { ctx, tile } = this;
    const wood = this.assets.tile("floor_wood");
    const carpet = this.assets.tile("floor_carpet");
    ctx.fillStyle = wood ? ctx.createPattern(wood, "repeat") : "#d8b982";
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    for (const zone of Object.values(this.scene.zones)) {
      if (zone.kind !== "company") continue;
      const [x, y, width, height] = rectFromZone(zone, tile);
      ctx.fillStyle = carpet ? ctx.createPattern(carpet, "repeat") : "#aaa59b";
      ctx.fillRect(x, y, width, height);
      ctx.save();
      ctx.globalAlpha = 0.16;
      ctx.fillStyle = zone.floor === "wood_cool" ? "#7188a4" : "#d6a85f";
      ctx.fillRect(x, y, width, height);
      ctx.restore();
    }
    this.drawFloorAmbient();
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

  drawWalls() {
    const { ctx, tile } = this;
    ctx.fillStyle = "#3b2b38";
    ctx.fillRect(0, 0, this.canvas.width, tile);
    const segment = this.assets.wall("segment");
    const plain = this.assets.wall("plain");
    let x = 0;
    let useSegment = true;
    while (x < this.canvas.width) {
      const image = useSegment ? segment : plain;
      const width = image?.naturalWidth || image?.width || (useSegment ? 256 : 128);
      if (image) ctx.drawImage(image, x, tile, width, 96);
      else {
        ctx.fillStyle = "#dfcfb6";
        ctx.fillRect(x, tile, width, 96);
      }
      x += width;
      useSegment = !useSegment;
    }
  }

  drawBottomWall() {
    const { ctx, tile } = this;
    const wallHeight = tile * 2;
    const wallY = this.canvas.height - wallHeight;
    ctx.fillStyle = "#5a4034";
    ctx.fillRect(0, wallY, this.canvas.width, wallHeight);
    ctx.fillStyle = "#b47a4e";
    ctx.fillRect(0, wallY, this.canvas.width, 2);

    const entrance = this.scene.zones.entrance?.rect;
    const door = this.scene.props.entrance || {
      tile: [
        entrance ? Math.floor((entrance[0] + entrance[2] - 5) / 2) : 17,
        Math.floor(this.canvas.height / tile) - 3,
      ],
      w: 6,
      h: 4,
      bottom_inset: 64,
    };
    const image = this.assets.prop("entrance", 176, 120);
    const width = image.naturalWidth || image.width || 176;
    const height = image.naturalHeight || image.height || 120;
    const bottomInset = door.bottom_inset ?? 64;
    const x = door.tile[0] * tile + (door.w * tile - width) / 2;
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
      const textOptions = { scale: 1, bold: true };
      const width = measurePixelText(zone.label, textOptions) + 18;
      const zoneLeft = x1 * tile;
      const zoneRight = (x2 + 1) * tile;
      const entrance = this.scene.props.entrance;
      const x = zone.kind === "entrance" && entrance
        ? (entrance.tile[0] + entrance.w / 2) * tile - width / 2
        : Math.min(zoneRight - width - 8, zoneLeft + 40);
      const y = zone.kind === "entrance"
        ? (this.backdrop ? 507 : y1 * tile - 54)
        : y1 * tile + 7;
      if (!this.backdrop || zone.kind !== "entrance") {
        ctx.fillStyle = "#3e291f";
        ctx.fillRect(x - 2, y - 2, width + 4, 18);
        ctx.fillStyle = "#8b603c";
        ctx.fillRect(x, y, width, 14);
        ctx.fillStyle = "#c99a62";
        ctx.fillRect(x + 2, y + 2, width - 4, 2);
      }
      drawPixelText(ctx, zone.label, x + 9, y + 1, {
        ...textOptions,
        color: "#fff0cd",
        shadow: "#3d281f",
        shadowX: 1,
        shadowY: 1,
      });
      ctx.restore();
    }
  }

  buildFurnitureLayers(timeSeconds, actors) {
    const { tile, scene, assets } = this;
    const layers = [];
    const under = [];

    for (const [id, desk] of Object.entries(scene.desks)) {
      const isHuman = id === (scene.human_id || "human");
      const deskImage = assets.prop("desk64", 108, 48);
      const width = deskImage.naturalWidth || deskImage.width || 108;
      const height = deskImage.naturalHeight || deskImage.height || 48;
      const footX = desk.tile[0] * tile + tile / 2;
      const footY = (desk.tile[1] + 2) * tile;
      layers.push({
        y: footY - 2,
        priority: -2,
        draw: () => {
          if (actors.get(id)?.isSeated) return;
          const chair = assets.prop("chair64", 39, 58);
          const chairWidth = chair.naturalWidth || chair.width || 39;
          const chairHeight = chair.naturalHeight || chair.height || 58;
          drawGroundShadow(this.ctx, footX, footY - 4, 13, 4);
          this.ctx.drawImage(
            chair,
            Math.round(footX - chairWidth / 2),
            Math.round(footY - chairHeight - 3),
            chairWidth,
            chairHeight,
          );
        },
      });
      layers.push({
        y: footY - 1,
        priority: -1,
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
          ctx.drawImage(
            deskImage,
            Math.round(footX - width / 2),
            Math.round(footY - height),
            width,
            height,
          );
        },
      });
      layers.push({
        y: footY,
        draw: () => this.drawDeskItems(id, footX, footY, height),
      });
    }

    for (const [name, prop] of Object.entries(scene.props)) {
      if (name === "plants" || name === "cat" ||
          name === "entrance") continue;
      if (this.backdrop && name !== "whiteboard") continue;
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
          if (prop.text) {
            drawPixelText(this.ctx, prop.text, x + drawWidth / 2, footY - drawHeight + 3, {
              scale: 1,
              bold: true,
              align: "center",
              color: "#4c3020",
            });
          }
          if (name === "server_rack") {
            this.ctx.fillStyle = Math.floor(timeSeconds * 4) % 2 ? "#6dff9a" : "#efba5e";
            this.ctx.fillRect(x + drawWidth - 15, footY - drawHeight + 12, 5, 5);
          }
        },
      });
    }

    for (const [xTile, yTile] of this.backdrop ? [] : (scene.props.plants || [])) {
      const width = tile;
      const x = xTile * tile;
      const footY = (yTile + 1) * tile;
      layers.push({
        y: footY,
        draw: () => {
          const image = assets.prop("plant_large", width, 56);
          const drawWidth = image.naturalWidth || image.width || width;
          const drawHeight = image.naturalHeight || image.height || 56;
          drawGroundShadow(this.ctx, x + drawWidth / 2, footY - 2, 12, 4);
          this.ctx.drawImage(image, x, footY - drawHeight, drawWidth, drawHeight);
        },
      });
    }
    return { under, layers };
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

  drawDeskItems(id, centerX, footY, deskHeight) {
    const hash = stableHash(id);
    const pcName = hash % 2 ? "pc_laptop" : "pc_desktop";
    const pc = this.assets.prop(pcName, pcName === "pc_laptop" ? 26 : 32, pcName === "pc_laptop" ? 18 : 24);
    const pcWidth = pc.naturalWidth || pc.width;
    const pcHeight = pc.naturalHeight || pc.height;
    const tabletopY = footY - deskHeight;
    const itemBottomY = tabletopY + 25;
    const pcBottomY = tabletopY + 25;
    this.ctx.drawImage(
      pc,
      Math.round(centerX - pcWidth / 2 - (pcName === "pc_desktop" ? 8 : 0)),
      Math.round(pcBottomY - pcHeight),
      pcWidth,
      pcHeight,
    );

    const sides = pcName === "pc_desktop"
      ? [{ cursor: centerX - 51, end: centerX - 26, direction: 1 },
        { cursor: centerX + 51, end: centerX + 10, direction: -1 }]
      : [{ cursor: centerX - 51, end: centerX - 15, direction: 1 },
        { cursor: centerX + 51, end: centerX + 15, direction: -1 }];
    const count = 2 + hash % 3;
    let mugs = 0;
    let placed = 0;
    const candidates = [...DESK_PROPS].sort((left, right) =>
      stableHash(`${id}:${left[0]}`) - stableHash(`${id}:${right[0]}`));
    for (const [index, [name, fallbackWidth, fallbackHeight]] of candidates.entries()) {
      if (placed >= count) break;
      const isMug = name.startsWith("prop_mug");
      if (isMug && mugs) continue;
      const image = this.assets.prop(name, fallbackWidth, fallbackHeight);
      const width = image.naturalWidth || image.width;
      const height = image.naturalHeight || image.height;
      const preferred = (hash >>> (index % 24)) & 1;
      const side = [sides[preferred], sides[1 - preferred]].find((candidate) =>
        candidate.direction > 0
          ? candidate.cursor + width <= candidate.end
          : candidate.cursor - width >= candidate.end);
      if (!side) continue;
      const x = side.direction > 0 ? side.cursor : side.cursor - width;
      side.cursor += side.direction * (width + 2);
      this.ctx.drawImage(image, Math.round(x), Math.round(itemBottomY - height), width, height);
      mugs += isMug ? 1 : 0;
      placed += 1;
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
      const companyZones = Object.values(this.scene.zones).filter((zone) => zone.kind === "company");
      const zone = companyZones.at(-1);
      const minX = zone ? zone.rect[0] + 1 : 1;
      const maxX = zone ? zone.rect[2] - 1 : Math.floor(this.canvas.width / this.tile) - 2;
      const minY = zone ? zone.rect[3] - 4 : 6;
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
    const image = this.assets.prop("cat", 28, 20);
    const width = image.naturalWidth || image.width || 28;
    const height = image.naturalHeight || image.height || 20;
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
    const ctx = this.ctx;
    ctx.save();
    const options = { scale: 1, bold: false, color: "#343039" };
    const left = x + 25;
    const innerWidth = 110;
    const surfaceBottom = y + 48;
    const lines = this.instructions.length
      ? this.instructions.slice(0, 3)
      : ["進行確認", "レビュー整理", "完了共有"];
    ctx.beginPath();
    ctx.rect(left, y + 7, innerWidth, surfaceBottom - y - 7);
    ctx.clip();
    drawPixelText(ctx, "今日の指示", left, y + 9, options);
    lines.forEach((line, index) => {
      const lineY = y + 24 + index * 11;
      if (lineY + 10 > surfaceBottom) return;
      let safe = String(line).replaceAll(/\s+/g, " ").slice(0, 22);
      while (safe && measurePixelText(`${index + 1}. ${safe}`, options) > innerWidth) safe = safe.slice(0, -1);
      drawPixelText(ctx, `${index + 1}. ${safe}`, left, lineY, options);
    });
    ctx.restore();
  }

  drawFixtureText() {
    const { ctx, tile } = this;
    const mat = this.scene.props.welcome_mat;
    if (mat) {
      const image = this.assets.prop("welcome_mat", 96, 48);
      const width = image.naturalWidth || image.width || 96;
      const height = image.naturalHeight || image.height || 48;
      const x = mat.tile[0] * tile;
      const y = (mat.tile[1] + mat.h) * tile - height;
      drawPixelText(ctx, "WELCOME", x + width / 2, y + 18, {
        scale: 1,
        bold: true,
        align: "center",
        color: "#d8efff",
      });
    }
  }

  drawHangingSign() {
    const ctx = this.ctx;
    const x = this.backdrop ? 190 : 32;
    const y = this.backdrop ? 0 : 34;
    const width = 280;
    const height = 42;
    ctx.save();
    if (!this.backdrop) {
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
    }
    drawPixelText(ctx, "ANIMAWORKS PIXEL OFFICE", x + 20, y + 15, {
      scale: 1,
      bold: true,
      color: "#fff0ca",
      shadow: "#2d1b14",
      shadowX: 1,
      shadowY: 1,
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
      scale: 1,
      bold: true,
      color: "#fff0ca",
      shadow: "#2d1b14",
      shadowX: 1,
      shadowY: 1,
    });
    ctx.restore();
  }

  // Color chips + short labels for work kinds (colors from WORK_KINDS only).
  drawWorkKindLegend() {
    const entries = Object.entries(WORK_KINDS)
      .filter(([, config]) => config.legend)
      .map(([key, config]) => ({ key, label: config.legend, color: config.border }));
    if (!entries.length) return;
    const textOptions = { scale: 1, bold: true };
    const chip = 6;
    const gap = 4;
    const rowH = 14;
    const padX = 6;
    const padY = 5;
    let maxLabelW = 0;
    for (const entry of entries) {
      maxLabelW = Math.max(maxLabelW, measurePixelText(entry.label, textOptions));
    }
    const innerW = chip + 4 + maxLabelW;
    const width = padX * 2 + innerW;
    const height = padY * 2 + entries.length * rowH - 2;
    const x = 8;
    const y = this.canvas.height - height - 8;
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = "rgba(30, 20, 16, 0.55)";
    ctx.fillRect(x, y, width, height);
    ctx.fillStyle = "rgba(251, 240, 228, 0.18)";
    ctx.fillRect(x + 1, y + 1, width - 2, height - 2);
    entries.forEach((entry, index) => {
      const rowY = y + padY + index * rowH;
      const chipX = x + padX;
      const chipY = rowY + 1;
      ctx.fillStyle = "#2a1a14";
      ctx.fillRect(chipX - 1, chipY - 1, chip + 2, chip + 2);
      ctx.fillStyle = entry.color;
      ctx.fillRect(chipX, chipY, chip, chip);
      drawPixelText(ctx, entry.label, chipX + chip + 4, rowY + 5, {
        ...textOptions,
        color: "#f5e6d0",
        baseline: "middle",
      });
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
