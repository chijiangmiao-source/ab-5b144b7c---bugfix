// Sample builders used by the "载入示例" menu and dimension changes.

export function emptyProblem() {
  return {
    rows: 4,
    cols: 5,
    depth: 8,
    s: 1,
    costs: [],
    forbidden: [],
  };
}

// A smooth synthetic OCT-like column: a bright band (low cost) whose depth
// meanders across the lateral grid, plus optional noise and a low-SNR gap.
export function syntheticProblem({ rows = 6, cols = 8, depth = 16, s = 2,
                                   noise = 60000, snrGap = false } = {}) {
  const costs = [];
  const forbidden = [];
  for (let i = 0; i < rows; i++) {
    const row = [];
    for (let j = 0; j < cols; j++) {
      const center =
        Math.round(depth * 0.45)
        + Math.round(Math.sin((j / Math.max(1, cols - 1)) * Math.PI * 1.6) * depth * 0.18)
        + Math.round(Math.cos((i / Math.max(1, rows - 1)) * Math.PI * 1.2) * depth * 0.10);
      const col = [];
      for (let k = 0; k < depth; k++) {
        const dist = Math.abs(k - center);
        const band = dist <= 1 ? 0 : 1000 * dist * dist;
        const n = Math.floor(Math.random() * noise);
        // Low-SNR region: flatten costs so a locally greedy picker jumps.
        const flat = snrGap && i === Math.floor(rows / 2) && j >= Math.floor(cols / 2);
        let v = flat ? 200000 + Math.floor(Math.random() * 40000)
                     : Math.min(1_000_000, band + n);
        col.push(v);
      }
      row.push(col);
    }
    costs.push(row);
  }
  return { rows, cols, depth, s, costs, forbidden };
}

// Hand-tied case: several columns carry identical cost vectors so the
// result is non-unique and the optional-depth ranges are visible.
export function ambiguousProblem() {
  const costs = [
    [[0, 0, 50], [10, 0, 40], [20, 0, 0]],
    [[0, 0, 50], [10, 0, 40], [20, 0, 0]],
    [[50, 0, 0], [40, 0, 10], [0, 0, 20]],
  ];
  return { rows: 3, cols: 3, depth: 3, s: 2, costs, forbidden: [] };
}

// Provably infeasible: s=0 forces one global depth, but every depth is
// excluded from at least one column.
export function infeasibleProblem() {
  return {
    rows: 2,
    cols: 2,
    depth: 3,
    s: 0,
    costs: [
      [[0, 10, 10], [10, 0, 10]],
      [[10, 10, 0], [0, 10, 10]],
    ],
    // depth 0 excluded in (0,1); depth 1 excluded in (1,0); depth 2 in (0,0)
    forbidden: [[0, 1, 0], [1, 0, 1], [0, 0, 2]],
  };
}
