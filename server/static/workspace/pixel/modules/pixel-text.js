const cache = new Map();

// Japanese pixel fonts (PixelMplus, M+ FONT LICENSE — see ../fonts/).
// Native design sizes: 10px / 12px. Render only at these sizes (or integer
// multiples via `scale`) to keep glyphs on the pixel grid.
const FONT_FILES = Object.freeze([
  ["PixelMplus10", "400", "PixelMplus10-Regular.ttf"],
  ["PixelMplus10", "700", "PixelMplus10-Bold.ttf"],
  ["PixelMplus12", "400", "PixelMplus12-Regular.ttf"],
  ["PixelMplus12", "700", "PixelMplus12-Bold.ttf"],
]);

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

const GLYPHS = Object.freeze({
  " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
  a: ["00000", "01110", "00001", "01111", "10001", "01111", "00000"],
  b: ["10000", "10000", "10110", "11001", "10001", "11110", "00000"],
  c: ["00000", "01110", "10000", "10000", "10001", "01110", "00000"],
  d: ["00001", "00001", "01101", "10011", "10001", "01111", "00000"],
  e: ["00000", "01110", "10001", "11111", "10000", "01111", "00000"],
  f: ["00110", "01001", "01000", "11100", "01000", "01000", "00000"],
  g: ["00000", "01111", "10001", "01111", "00001", "01110", "00000"],
  h: ["10000", "10000", "10110", "11001", "10001", "10001", "00000"],
  i: ["00100", "00000", "01100", "00100", "00100", "01110", "00000"],
  j: ["00010", "00000", "00110", "00010", "10010", "01100", "00000"],
  k: ["10000", "10010", "10100", "11000", "10100", "10010", "00000"],
  l: ["01100", "00100", "00100", "00100", "00100", "01110", "00000"],
  m: ["00000", "11010", "10101", "10101", "10101", "10101", "00000"],
  n: ["00000", "10110", "11001", "10001", "10001", "10001", "00000"],
  o: ["00000", "01110", "10001", "10001", "10001", "01110", "00000"],
  p: ["00000", "11110", "10001", "11110", "10000", "10000", "00000"],
  q: ["00000", "01111", "10001", "01111", "00001", "00001", "00000"],
  r: ["00000", "10110", "11001", "10000", "10000", "10000", "00000"],
  s: ["00000", "01111", "10000", "01110", "00001", "11110", "00000"],
  t: ["01000", "01000", "11100", "01000", "01001", "00110", "00000"],
  u: ["00000", "10001", "10001", "10001", "10011", "01101", "00000"],
  v: ["00000", "10001", "10001", "10001", "01010", "00100", "00000"],
  w: ["00000", "10001", "10101", "10101", "10101", "01010", "00000"],
  x: ["00000", "10001", "01010", "00100", "01010", "10001", "00000"],
  y: ["00000", "10001", "10001", "01111", "00001", "01110", "00000"],
  z: ["00000", "11111", "00010", "00100", "01000", "11111", "00000"],
  F: ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
  S: ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
  0: ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
  1: ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
  2: ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
  3: ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
  4: ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
  5: ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
  6: ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
  7: ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
  8: ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
  9: ["01110", "10001", "10001", "01111", "00001", "00010", "11100"],
  ".": ["00000", "00000", "00000", "00000", "00000", "00110", "00110"],
  ",": ["00000", "00000", "00000", "00000", "00110", "00100", "01000"],
  ":": ["00000", "00110", "00110", "00000", "00110", "00110", "00000"],
  "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
  "_": ["00000", "00000", "00000", "00000", "00000", "00000", "11111"],
  "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
  "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"],
  ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"],
});

function rasterizeBitmap(value, color, letterSpacing = 1) {
  const glyphs = [...value].map((character) => GLYPHS[character] || GLYPHS[character.toLowerCase()]);
  if (glyphs.some((glyph) => !glyph)) return null;
  const spacing = Math.max(0, Math.round(letterSpacing));
  const advance = 5 + spacing;
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, glyphs.length * advance - spacing);
  canvas.height = 7;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = color;
  glyphs.forEach((glyph, glyphIndex) => {
    glyph.forEach((row, y) => {
      [...row].forEach((pixel, x) => {
        if (pixel === "1") ctx.fillRect(glyphIndex * advance + x, y, 1, 1);
      });
    });
  });
  return { canvas, width: canvas.width, height: canvas.height };
}

function rasterize(text, options = {}) {
  const value = String(text);
  const fontSize = options.fontSize || 6;
  const color = options.color || "#ffffff";
  const weight = options.bold === false ? "400" : "700";
  const letterSpacing = options.letterSpacing ?? 1;
  const key = `${value}|${fontSize}|${color}|${weight}|${options.bitmap !== false}|${letterSpacing}`;
  if (cache.has(key)) return cache.get(key);

  const bitmap = options.bitmap === false ? null : rasterizeBitmap(value, color, letterSpacing);
  if (bitmap) {
    cache.set(key, bitmap);
    return bitmap;
  }

  // Snap to the nearest native PixelMplus size so glyphs stay on the grid.
  const size = fontSize <= 10 ? 10 : 12;
  const font = `${weight} ${size}px PixelMplus${size}, monospace`;
  const probe = document.createElement("canvas").getContext("2d");
  probe.font = font;
  const width = Math.max(1, Math.ceil(probe.measureText(value).width) + 2);
  const height = size + 2;
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
  const scale = Math.max(1, Math.round(options.scale || 2));
  return rasterize(text, options).width * scale;
}

export function drawPixelText(ctx, text, x, y, options = {}) {
  const scale = Math.max(1, Math.round(options.scale || 2));
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
