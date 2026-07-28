import { drawPixelText } from "./pixel-text.js";
import { resolveBasePath } from "./scene-layout.js";

const ASSET_ROOT = new URL("../assets/", import.meta.url);

const SAMPLE_COLORS = Object.freeze([
  "#ef7f8f", "#34466f", "#684077", "#e6d5b8",
  "#eaa5bb", "#72bce4", "#68a66b", "#9b71b3",
]);

const DEFAULT_ANIMS = Object.freeze({
  idle: { row: 0, frames: 4, fps: 4 },
  working: { row: 1, frames: 4, fps: 8 },
  thinking: { row: 2, frames: 4, fps: 4 },
  talking: { row: 3, frames: 4, fps: 8 },
  walk_down: { row: 4, frames: 4, fps: 8 },
  walk_up: { row: 5, frames: 4, fps: 8 },
  walk_side: { row: 6, frames: 4, fps: 8 },
  sleeping: { row: 7, frames: 4, fps: 2 },
  success: { row: 8, frames: 4, fps: 8 },
  error: { row: 9, frames: 4, fps: 5 },
});

function canvas(width, height) {
  const target = document.createElement("canvas");
  target.width = width;
  target.height = height;
  return target;
}

function loadImage(url) {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = url;
  });
}

function runtimeAssetUrl(file) {
  const encodedPath = String(file).split("/").map(encodeURIComponent).join("/");
  return `${resolveBasePath()}/api/workspace/pixel/assets/${encodedPath}`;
}

async function fetchRuntimeAsset(file) {
  try {
    const response = await fetch(runtimeAssetUrl(file), { cache: "no-store" });
    return response.ok ? response : null;
  } catch {
    return null;
  }
}

async function imageFromResponse(response) {
  const objectUrl = URL.createObjectURL(await response.blob());
  try {
    return await loadImage(objectUrl);
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

async function loadDeclaredImage(file, bundledUrl) {
  const runtimeResponse = await fetchRuntimeAsset(file);
  if (runtimeResponse) {
    const runtimeImage = await imageFromResponse(runtimeResponse);
    if (runtimeImage) return runtimeImage;
  }
  return loadImage(bundledUrl);
}

function shade(hex, amount) {
  const value = Number.parseInt(hex.slice(1), 16);
  const channel = (shift) => Math.max(0, Math.min(255, ((value >> shift) & 255) + amount));
  return `rgb(${channel(16)},${channel(8)},${channel(0)})`;
}

function stableHash(value) {
  let hash = 2166136261;
  for (const char of String(value || "")) {
    hash ^= char.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function sampleKey(id) {
  const trailing = /(\d+)\s*$/.exec(String(id));
  const index = trailing ? (parseInt(trailing[1], 10) - 1) % 6 : stableHash(id) % 6;
  return `sample_${String(index + 1).padStart(2, "0")}`;
}

function placeholderCharacter(id, frameW = 64, frameH = 64) {
  const sheet = canvas(frameW * 4, frameH * 10);
  const ctx = sheet.getContext("2d");
  const color = SAMPLE_COLORS[stableHash(id) % SAMPLE_COLORS.length];

  for (let row = 0; row < 10; row += 1) {
    for (let frame = 0; frame < 4; frame += 1) {
      const x = frame * frameW;
      const y = row * frameH;
      const bob = frame % 2;
      ctx.fillStyle = "#2a202b99";
      ctx.fillRect(x + 18, y + 58, 28, 3);
      ctx.fillStyle = shade(color, -35);
      ctx.fillRect(x + 20, y + 35 + bob, 24, 24 - bob);
      ctx.fillStyle = color;
      ctx.fillRect(x + 16, y + 17 + bob, 32, 25);
      ctx.fillStyle = "#f2d0b5";
      ctx.fillRect(x + 21, y + 22 + bob, 22, 17);
      ctx.fillStyle = "#2e2530";
      ctx.fillRect(x + 25, y + 29 + bob, 3, 3);
      ctx.fillRect(x + 36, y + 29 + bob, 3, 3);
      if (row === 1) {
        ctx.fillStyle = "#f2d0b5";
        ctx.fillRect(x + 11 + frame * 2, y + 45, 8, 5);
      } else if (row === 2) {
        ctx.fillStyle = "#f2d0b5";
        ctx.fillRect(x + 42, y + 36 - frame, 7, 7);
      } else if (row === 3) {
        ctx.fillStyle = "#58353a";
        ctx.fillRect(x + 30, y + 35, 5, frame % 2 ? 2 : 4);
      } else if (row >= 4 && row <= 6) {
        ctx.fillStyle = shade(color, -60);
        ctx.fillRect(x + 20 + (frame % 2) * 3, y + 56, 8, 6);
        ctx.fillRect(x + 36 - (frame % 2) * 3, y + 56, 8, 6);
      } else if (row === 7) {
        ctx.fillStyle = "#dce8ff";
        drawPixelText(ctx, "z", x + 45 + frame, y + 18 - frame * 2, {
          fontSize: 5,
          scale: 2,
          color: "#fff6de",
        });
      } else if (row === 8) {
        ctx.fillStyle = "#ffe580";
        ctx.fillRect(x + 10, y + 12 + frame, 5, 5);
        ctx.fillRect(x + 50, y + 18 - frame, 4, 4);
      } else if (row === 9) {
        ctx.fillStyle = "#ef6b64";
        ctx.fillRect(x + 28, y + 8, 8, 8);
      }
      ctx.fillStyle = "#fff";
      drawPixelText(ctx, id.toLowerCase(), x + frameW / 2, y + 48, {
        fontSize: 4,
        scale: 2,
        align: "center",
        color: "#fff6de",
      });
    }
  }
  return sheet;
}

function placeholderProp(label, width, height, color = "#87694f") {
  const image = canvas(width, height);
  const ctx = image.getContext("2d");
  if (label === "rug") {
    ctx.fillStyle = "#714f52";
    ctx.fillRect(2, 2, width - 4, height - 4);
    ctx.fillStyle = "#b78369";
    ctx.fillRect(8, 8, width - 16, height - 16);
    ctx.strokeStyle = "#e0bd8f";
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(11, 11, width - 22, height - 22);
    return image;
  }
  if (label === "chair") {
    ctx.fillStyle = "#50382f";
    ctx.fillRect(5, 2, width - 10, Math.max(12, height - 16));
    ctx.fillStyle = "#936846";
    ctx.fillRect(8, 5, width - 16, Math.max(7, height - 22));
    ctx.fillStyle = "#3b2925";
    ctx.fillRect(8, height - 16, width - 16, 12);
    ctx.fillRect(6, height - 6, 5, 6);
    ctx.fillRect(width - 11, height - 6, 5, 6);
    return image;
  }
  if (label === "trash_bin") {
    ctx.fillStyle = "#584e49";
    ctx.fillRect(6, 6, width - 12, height - 8);
    ctx.fillStyle = "#8b7e70";
    ctx.fillRect(3, 3, width - 6, 6);
    ctx.fillStyle = "#302a29";
    for (let x = 10; x < width - 7; x += 6) ctx.fillRect(x, 12, 2, height - 18);
    return image;
  }
  ctx.fillStyle = "#2b2028";
  ctx.fillRect(2, 6, width - 2, height - 6);
  ctx.fillStyle = color;
  ctx.fillRect(0, 0, width - 4, height - 8);
  ctx.strokeStyle = shade(color, 38);
  ctx.lineWidth = 3;
  ctx.strokeRect(3, 3, width - 10, height - 14);
  drawPixelText(ctx, String(label).replaceAll("_", " ").slice(0, 14), width / 2 - 2, height / 2 - 3, {
    fontSize: 5,
    scale: 2,
    align: "center",
    baseline: "middle",
    color: "#fff6de",
  });
  return image;
}

function placeholderFx(label) {
  const image = canvas(128, 48);
  const ctx = image.getContext("2d");
  ctx.fillStyle = "#2a202d";
  ctx.fillRect(5, 5, 118, 34);
  ctx.fillStyle = "#fff8df";
  ctx.fillRect(2, 2, 118, 34);
  ctx.fillRect(20, 34, 10, 8);
  ctx.strokeStyle = "#7b5f65";
  ctx.lineWidth = 2;
  ctx.strokeRect(2, 2, 118, 34);
  drawPixelText(ctx, label, 61, 19, {
    fontSize: 5,
    scale: 2,
    align: "center",
    baseline: "middle",
    color: "#392d34",
  });
  return image;
}

export class AssetStore {
  constructor(manifest = {}) {
    this.manifest = manifest;
    this.images = new Map();
    this.placeholders = new Map();
    this.runtimeCharacters = new Map();
  }

  static async load(animas = [], options = {}) {
    let manifest = {};
    const runtimeManifest = await fetchRuntimeAsset("manifest.json");
    if (runtimeManifest) {
      try {
        manifest = await runtimeManifest.json();
      } catch {
        manifest = {};
      }
    }
    if (!Object.keys(manifest).length) {
      try {
        const response = await fetch(new URL("manifest.json", ASSET_ROOT), { cache: "no-store" });
        if (response.ok) manifest = await response.json();
      } catch {
        manifest = {};
      }
    }
    const store = new AssetStore(manifest);
    await store.loadDeclaredImages();
    if (options.runtime !== false) await store.loadRuntimeCharacters(animas);
    return store;
  }

  async loadRuntimeCharacters(animas) {
    const basePath = resolveBasePath();
    await Promise.all((Array.isArray(animas) ? animas : []).map(async (anima) => {
      if (!anima?.name || anima.is_human) return;
      const id = String(anima.name).trim().toLowerCase();
      const name = encodeURIComponent(String(anima.name));
      const url = `${basePath}/api/animas/${name}/assets/pixel_sheet.png?fresh=${Date.now()}`;
      const image = await loadImage(url);
      if (image) this.runtimeCharacters.set(id, image);
    }));
  }

  async loadDeclaredImages() {
    const entries = [];
    const visit = (node, prefix = "") => {
      if (!node || typeof node !== "object") return;
      if (typeof node.file === "string") entries.push([prefix, node.file]);
      for (const [key, value] of Object.entries(node)) {
        if (key !== "file") visit(value, prefix ? `${prefix}.${key}` : key);
      }
    };
    visit(this.manifest);
    const freshAssets = new Set([
      "scene.tiles.carpet_blue",
      "scene.tiles.mat",
      "scene.props.sofa",
      "scene.props.rug",
      "scene.props.side_table",
      "scene.props.bookshelf_b",
      "scene.props.poster_a",
      "scene.props.poster_b",
    ]);
    await Promise.all(entries.map(async ([key, file]) => {
      const url = new URL(file, ASSET_ROOT);
      if (freshAssets.has(key)) {
        url.searchParams.set("fresh", String(Date.now()));
      }
      const image = await loadDeclaredImage(file, url);
      if (image) this.images.set(key, image);
    }));
  }

  character(id) {
    const normalized = String(id || "").toLowerCase();
    const declared = ["human", "customer_a", "customer_b"].includes(normalized)
      ? normalized
      : sampleKey(normalized);
    const config = this.manifest.chars?.[declared] || {};
    const runtimeImage = this.runtimeCharacters.get(normalized);
    const image = runtimeImage || this.images.get(`chars.${declared}`);
    const frameW = config.frameW || 96;
    const frameH = config.frameH || 96;
    const key = `char:${id}:${frameW}:${frameH}`;
    if (!image && !this.placeholders.has(key)) {
      this.placeholders.set(key, placeholderCharacter(normalized, frameW, frameH));
    }
    return {
      image: image || this.placeholders.get(key),
      frameW,
      frameH,
      anims: { ...DEFAULT_ANIMS, ...(config.anims || {}) },
      placeholder: !image,
    };
  }

  tile(name) {
    return this.images.get(`scene.tiles.${name}`) || null;
  }

  wall(mode) {
    return this.images.get(`scene.walls.${mode}`) || null;
  }

  wallBottom() {
    return this.images.get("scene.walls.wall_bottom") || null;
  }

  prop(name, width = 96, height = 64) {
    const image = this.images.get(`scene.props.${name}`);
    if (image) return image;
    const key = `prop:${name}:${width}:${height}`;
    if (!this.placeholders.has(key)) {
      const colors = {
        desk: "#8d684a", desk_human: "#745239", meeting_table: "#9b7450",
        whiteboard: "#d8d5c6", plant: "#557c52", door: "#704b3f",
        side_table: "#79583e", cat: "#4e4543",
      };
      this.placeholders.set(key, placeholderProp(name, width, height, colors[name] || "#806d5b"));
    }
    return this.placeholders.get(key);
  }

  item(id) {
    const raw = String(id ?? "1");
    const itemName = /^item_\d{2}$/.test(raw)
      ? raw
      : `item_${String((stableHash(raw) % 14) + 1).padStart(2, "0")}`;
    const image = this.images.get(`scene.items.${itemName}`);
    if (image) return image;
    const key = `item:${itemName}`;
    if (!this.placeholders.has(key)) {
      this.placeholders.set(key, placeholderProp(itemName, 32, 32, "#806d5b"));
    }
    return this.placeholders.get(key);
  }

  fx(name, label = name) {
    const image = this.images.get(`fx.${name}`);
    if (image) return image;
    const key = `fx:${name}:${label}`;
    if (!this.placeholders.has(key)) this.placeholders.set(key, placeholderFx(label));
    return this.placeholders.get(key);
  }

  fxDefinition(name, label = name) {
    const config = this.manifest.fx?.[name] || {};
    const image = this.fx(name, label);
    const isReal = this.images.get(`fx.${name}`) === image;
    if (!isReal) {
      return {
        image,
        row: 0,
        frames: 1,
        fps: 1,
        frameW: image.width,
        frameH: image.height,
      };
    }
    const frames = Math.max(1, config.frames || 1);
    const sameFile = Object.values(this.manifest.fx || {})
      .filter((entry) => entry.file === config.file);
    const rows = Math.max(1, ...sameFile.map((entry) => (entry.row || 0) + 1));
    return {
      image,
      row: config.row || 0,
      frames,
      fps: config.fps || 1,
      frameW: config.frameW || image.naturalWidth / frames,
      frameH: config.frameH || image.naturalHeight / rows,
    };
  }
}
