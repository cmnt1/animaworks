/**
 * Convert browser client coordinates to the canvas's logical pixel space.
 * Returns null for invalid dimensions or coordinates outside the displayed
 * canvas rectangle.
 *
 * @param {number} clientX
 * @param {number} clientY
 * @param {{ left: number, top: number, width: number, height: number }} rect
 * @param {number} logicalWidth
 * @param {number} logicalHeight
 * @returns {{ x: number, y: number }|null}
 */
export function clientToCanvasPoint(clientX, clientY, rect, logicalWidth, logicalHeight) {
  const width = Number(rect?.width);
  const height = Number(rect?.height);
  const canvasWidth = Number(logicalWidth);
  const canvasHeight = Number(logicalHeight);
  const left = Number(rect?.left);
  const top = Number(rect?.top);
  if (![clientX, clientY, left, top, width, height, canvasWidth, canvasHeight].every(Number.isFinite) ||
      width <= 0 || height <= 0 || canvasWidth <= 0 || canvasHeight <= 0) {
    return null;
  }

  const x = (clientX - left) * canvasWidth / width;
  const y = (clientY - top) * canvasHeight / height;
  if (x < 0 || y < 0 || x > canvasWidth || y > canvasHeight) return null;
  return { x, y };
}

/**
 * Find the frontmost actor under a client-space pointer position.
 * `actors` must be ordered back-to-front using the same order as rendering;
 * the final matching entry is therefore the one drawn on top.
 *
 * Actor bounds use logical canvas coordinates: { name, x, y, width, height }.
 *
 * @param {{ clientX: number, clientY: number, rect: object,
 *   logicalWidth: number, logicalHeight: number, actors: Array<object> }} options
 * @returns {string|null}
 */
export function hitTestAnima({
  clientX,
  clientY,
  rect,
  logicalWidth,
  logicalHeight,
  actors = [],
}) {
  const point = clientToCanvasPoint(clientX, clientY, rect, logicalWidth, logicalHeight);
  if (!point || !Array.isArray(actors)) return null;

  for (let index = actors.length - 1; index >= 0; index -= 1) {
    const actor = actors[index];
    const x = Number(actor?.x);
    const y = Number(actor?.y);
    const width = Number(actor?.width);
    const height = Number(actor?.height);
    if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) continue;
    if (point.x >= x && point.x <= x + width && point.y >= y && point.y <= y + height) {
      const name = actor.name ?? actor.id;
      return name == null ? null : String(name);
    }
  }
  return null;
}
