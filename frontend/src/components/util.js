// Robust access to the cost vector of one lateral column from a draft.
// Accepts both nested costs[R][C][D] and a flat row-major costs vector.
export function columnCosts(obj, i, j) {
  if (!obj) return null;
  const { rows, cols, depth, costs } = obj;
  if (!Array.isArray(costs)) return null;
  if (costs.length > 0 && typeof costs[0] === "number") {
    const start = (i * cols + j) * depth;
    return costs.slice(start, start + depth);
  }
  return costs?.[i]?.[j] ?? null;
}

export function isForbidden(obj, i, j, k) {
  const list = obj?.forbidden;
  if (!Array.isArray(list)) return false;
  return list.some(([a, b, c]) => a === i && b === j && c === k);
}

// 0..1 normalised cost -> perceptually simple blue->white->red-ish scale.
export function costColor(v, max = 1_000_000) {
  const t = Math.max(0, Math.min(1, v / max));
  // Low cost: deep blue; high cost: warm amber.
  const hue = (1 - t) * 215; // 215 (blue) -> 0 (red)
  const sat = 70;
  const light = 85 - t * 45; // 85% (near white) -> 40%
  return `hsl(${hue} ${sat}% ${light}%)`;
}

export function depthColor(t) {
  // Canonical depth colour used in the top view: shallow cyan -> deep indigo.
  const x = Math.max(0, Math.min(1, t));
  const hue = 190 - x * 170;
  return `hsl(${hue} 65% ${62 - x * 18}%)`;
}
