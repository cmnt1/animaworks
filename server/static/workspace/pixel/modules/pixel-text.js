const cache = new Map();

// Japanese pixel font (PixelMplus, M+ FONT LICENSE — see ../fonts/).
// Native design size: 10px. Render only at 10px (or integer multiples via
// `scale`) to keep glyphs on the pixel grid.
const FONT_FILES = Object.freeze([
  ["PixelMplus10", "400", "PixelMplus10-Regular.ttf"],
  ["PixelMplus10", "700", "PixelMplus10-Bold.ttf"],
]);

const FONT_SIZE = 10;

let fontsReady = false;
let fontsPromise = null;

export function preloadPixelFonts() {
  if (fontsPromise) return fontsPromise;
  fontsPromise = Promise.all(
    FONT_FILES.map(([family, weight, file]) => {
      const face = new FontFace(
        family,
        `url(${new URL(`../fonts/${file}`, import.meta.url)})`,
        { weight },
      );
      document.fonts.add(face);
      return face.load();
    }),
  ).then(() => {
    fontsReady = true;
  }).catch(() => {
    // Missing fonts degrade to monospace fallback; keep rendering.
    fontsReady = true;
  });
  return fontsPromise;
}

function rasterize(text, options = {}) {
  const value = String(text);
  const color = options.color || "#ffffff";
  const weight = options.bold === false ? "400" : "700";
  // fontSize / bitmap are accepted for call-site compatibility but ignored.
  const key = `${value}|${color}|${weight}`;
  if (cache.has(key)) return cache.get(key);

  const font = `${weight} ${FONT_SIZE}px PixelMplus10, monospace`;
  const probe = document.createElement("canvas").getContext("2d");
  probe.font = font;
  const width = Math.max(1, Math.ceil(probe.measureText(value).width) + 2);
  const height = FONT_SIZE + 2;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  ctx.font = font;
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillStyle = color;
  ctx.fillText(value, 1, 1);

  const pixels = ctx.getImageData(0, 0, width, height);
  for (let index = 3; index < pixels.data.length; index += 4) {
    pixels.data[index] = pixels.data[index] >= 96 ? 255 : 0;
  }
  ctx.putImageData(pixels, 0, 0);

  const result = { canvas, width, height };
  if (fontsReady) cache.set(key, result);
  return result;
}

export function measurePixelText(text, options = {}) {
  const scale = Math.max(1, Math.round(options.scale || 1));
  return rasterize(text, options).width * scale;
}

export function drawPixelText(ctx, text, x, y, options = {}) {
  const scale = Math.max(1, Math.round(options.scale || 1));
  const align = options.align || "left";
  const baseline = options.baseline || "top";
  const color = options.color || "#fff5dc";
  const main = rasterize(text, { ...options, color });
  const width = main.width * scale;
  const height = main.height * scale;
  let dx = Math.round(x);
  let dy = Math.round(y);
  if (align === "center") dx -= Math.round(width / 2);
  else if (align === "right") dx -= width;
  if (baseline === "middle") dy -= Math.round(height / 2);
  else if (baseline === "bottom") dy -= height;

  ctx.save();
  ctx.imageSmoothingEnabled = false;
  if (options.shadow) {
    const shadow = rasterize(text, { ...options, color: options.shadow });
    const offsetX = options.shadowX ?? scale;
    const offsetY = options.shadowY ?? scale;
    ctx.drawImage(shadow.canvas, dx + offsetX, dy + offsetY, width, height);
  }
  ctx.drawImage(main.canvas, dx, dy, width, height);
  ctx.restore();
  return { width, height };
}
