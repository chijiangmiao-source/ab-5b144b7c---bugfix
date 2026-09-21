"""
Exact integer solver for a single layered surface extracted from an OCT
cost volume.

Problem
-------
Volume shape (rows R, cols C, depth D).  A surface chooses exactly one
depth z[r, c] in {0 .. D-1} for every lateral column (r, c):

    minimise   sum cost[r, c, z[r, c]]
    subject to |z[r,c] - z[r',c']| <= S   for every 4-neighbour pair
               z[r, c] not in forbidden set

All costs are non-negative integers; the answer must be an exact integer.

Algorithm (no general-purpose optimiser is used)
------------------------------------------------
This is a multi-labelling MRF on a grid with convex pairwise potential
(hard slope limit).  For linearly ordered labels it is reducible exactly
to an integer s-t minimum cut (the monotone-chain construction):

* for every column t, nodes v(t,1) ... v(t,D-1) are threshold nodes,
  v(t,0) is the source and v(t,D) is the sink; a cut labels the column
  with z(t) = max { k : v(t,k) is on the source side };
* infinite-capacity chain edges v(t,k) -> v(t,k-1) make source-side sets
  prefixes, so every finite cut encodes one well-defined depth;
* unary cost differences cost[k]-cost[k-1] become v_k -> sink (positive
  difference) or source -> v_k (negative difference) edges;
* forbidden depth a is excluded by an infinite edge v(t,a) -> v(t,a+1);
* the pairwise slope limit becomes infinite cross edges
  v(q,k+S) -> v(p,k) in both directions for each 4-neighbour pair.

Maximum flow is computed with a hand-written, integer-capacity
ISAP (improved shortest augmenting path) implementation in
``isap.py``.  After the flow, the residual graph classifies every
threshold node exactly (the Picard-Queyranne min-cut lattice):

* the set reachable from the source is the component-wise smallest
  minimum cut, hence its labels are exactly the lexicographically
  smallest row-major depth vector among all optima;
* the set of nodes that can reach the sink is the complement of the
  component-wise largest minimum cut;
* depth a is attainable at column t in some optimal surface iff the
  cut may simultaneously put v(t,a) on the source side and v(t,a+1)
  on the sink side: v(t,a) cannot reach the sink, the source cannot
  reach v(t,a+1), and no residual path v(t,a) ~> v(t,a+1) exists.
  The infinite chain arc v(t,a+1) -> v(t,a) always keeps residual
  capacity (total flow is strictly below "infinite" whenever the
  instance is feasible), so the last condition holds exactly when
  the two thresholds lie in different strongly connected components.

All three conditions are evaluated exactly: one residual BFS from the
source, one reverse residual BFS from the sink, and one Kosaraju SCC
decomposition -- no approximation is involved at any problem size.
"""

from __future__ import annotations

from dataclasses import dataclass

from .isap import ISAP

# Cost range for one voxel; the "infinite" cut capacity is derived in
# solve() as rows*cols*depth*COST_MAX + 1.
COST_MAX = 1_000_000


class ValidationError(Exception):
    """Payload does not describe a valid problem; ``errors`` locates causes."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class SolveResult:
    status: str                      # "feasible" | "infeasible"
    rows: int
    cols: int
    depth: int
    s: int
    optimal_cost: int | None
    canonical_depth: list[list[int]] | None
    optional_depths: list[list[list[int]]] | None
    canonical_cost: list[list[int]] | None
    unique: bool | None
    ambiguous_columns: int


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_input(payload: dict):
    """Validate raw JSON. Returns R, C, D, flat costs[R*C][D], forbidden sets, S."""
    errors: list[str] = []

    if not isinstance(payload, dict):
        raise ValidationError(["请求体必须是 JSON 对象"])

    rows = payload.get("rows")
    cols = payload.get("cols")
    depth = payload.get("depth")
    s_param = payload.get("s")

    dims: dict[str, int] = {}
    for name, value, hi in (("rows", rows, 40), ("cols", cols, 40), ("depth", depth, 64)):
        if not _is_int(value):
            errors.append(f"维度 {name} 必须是整数")
        elif not 2 <= value <= hi:
            errors.append(f"维度 {name}={value} 非法，允许范围 [2, {hi}]")
        else:
            dims[name] = value

    if not _is_int(s_param):
        errors.append("参数 s（四邻深度差上限）必须是整数")
    elif s_param < 0:
        errors.append(f"参数 s={s_param} 不能为负数")
    if errors:
        raise ValidationError(errors)

    r, c, d = dims["rows"], dims["cols"], dims["depth"]
    s = s_param

    # ---- costs: nested R x C x D array, or one flat row-major vector ------
    flat_costs: list[list[int]] = []
    costs_raw = payload.get("costs")
    MISSING = object()
    if costs_raw is None:
        errors.append("缺少必填字段 costs（整数代价数据）")
    else:
        flat_mode = isinstance(costs_raw, list) and (
            len(costs_raw) == 0 or not isinstance(costs_raw[0], list)
        )
        expected = r * c * d
        if flat_mode:
            if not isinstance(costs_raw, list):
                errors.append("costs 必须是数组")
            elif len(costs_raw) != expected:
                errors.append(
                    f"costs 为扁平数组时长度必须是 rows*cols*depth={expected}，"
                    f"实际为 {len(costs_raw)}"
                )
            else:
                bad_index = None
                for idx, v in enumerate(costs_raw):
                    if not _is_int(v):
                        errors.append(f"costs[{idx}] 不是整数")
                        bad_index = idx
                        break
                    if not 0 <= v <= COST_MAX:
                        errors.append(f"costs[{idx}]={v} 超出允许范围 [0, 1000000]")
                        bad_index = idx
                        break
                if bad_index is None:
                    for t in range(r * c):
                        flat_costs.append(list(costs_raw[t * d:(t + 1) * d]))
        else:
            if not isinstance(costs_raw, list) or len(costs_raw) != r:
                errors.append(f"costs 必须是长度为 rows={r} 的三维数组")
            else:
                for i, row in enumerate(costs_raw):
                    if not isinstance(row, list) or len(row) != c:
                        errors.append(f"costs[{i}] 必须是长度为 cols={c} 的数组")
                        continue
                    for j, col in enumerate(row):
                        where = f"costs[{i}][{j}]"
                        if not isinstance(col, list) or len(col) != d:
                            errors.append(f"{where} 必须是长度为 depth={d} 的整数数组")
                            continue
                        for k, v in enumerate(col):
                            if not _is_int(v):
                                errors.append(f"{where}[{k}] 不是整数")
                                break
                            if not 0 <= v <= COST_MAX:
                                errors.append(f"{where}[{k}]={v} 超出允许范围 [0, 1000000]")
                                break
                        else:
                            flat_costs.append(list(col))

    # ---- forbidden voxel triples ------------------------------------------
    forbidden: list[set[int]] = [set() for _ in range(r * c)]
    forbidden_raw = payload.get("forbidden", MISSING)
    if forbidden_raw is MISSING or forbidden_raw is None:
        forbidden_raw = []
    if not isinstance(forbidden_raw, list):
        errors.append("forbidden 必须是 [row, col, depth] 三元组的数组")
    else:
        seen: set[tuple[int, int, int]] = set()
        for idx, item in enumerate(forbidden_raw):
            if not (
                isinstance(item, list)
                and len(item) == 3
                and all(_is_int(v) for v in item)
            ):
                errors.append(f"forbidden[{idx}] 必须是形如 [row, col, depth] 的整数三元组")
                continue
            i, j, k = item
            if not (0 <= i < r and 0 <= j < c and 0 <= k < d):
                errors.append(
                    f"forbidden[{idx}]=[{i}, {j}, {k}] 坐标越界"
                    f"（合法范围 row<{r}, col<{c}, depth<{d}）"
                )
                continue
            if (i, j, k) in seen:
                errors.append(f"forbidden[{idx}]=[{i}, {j}, {k}] 与之前条目重复")
                continue
            seen.add((i, j, k))
            forbidden[i * c + j].add(k)

    if errors or len(flat_costs) != r * c:
        # Structural cost errors were already reported; stop before solving.
        if not errors and len(flat_costs) != r * c:
            errors.append("costs 结构不完整，无法求解")
        raise ValidationError(errors)

    return r, c, d, flat_costs, forbidden, s


def _result_from_columns(
    r: int, c: int, d: int, s: int,
    canonical_flat: list[int], optional_flat: list[list[int]],
    total: int, costs: list[list[int]] | None = None,
) -> SolveResult:
    canonical = [[canonical_flat[i * c + j] for j in range(c)] for i in range(r)]
    optional = [[optional_flat[i * c + j] for j in range(c)] for i in range(r)]
    canonical_cost = (
        [[costs[i * c + j][canonical[i][j]] for j in range(c)] for i in range(r)]
        if costs is not None else None
    )
    ambiguous = sum(1 for opts in optional_flat if len(opts) != 1)
    return SolveResult(
        status="feasible", rows=r, cols=c, depth=d, s=s,
        optimal_cost=total, canonical_depth=canonical,
        optional_depths=optional, canonical_cost=canonical_cost,
        unique=(ambiguous == 0), ambiguous_columns=ambiguous,
    )


def _infeasible(r: int, c: int, d: int, s: int) -> SolveResult:
    return SolveResult(
        status="infeasible", rows=r, cols=c, depth=d, s=s,
        optimal_cost=None, canonical_depth=None, optional_depths=None,
        canonical_cost=None, unique=None, ambiguous_columns=0,
    )


def solve(payload: dict) -> SolveResult:
    r, c, d, costs, forbidden, s = validate_input(payload)
    n = r * c

    # ---- Exact special cases of the same integer min-cut model -----------
    # Both are direct evaluations of the objective under constraints that
    # collapse to a trivial form; results are provably identical to the
    # general construction below.

    # S = 0 and the lateral grid is connected (rectangle, r,c >= 2):
    # |z_p - z_q| <= 0 forces a single global depth for all columns.
    if s == 0:
        common = [k for k in range(d) if all(k not in forbidden[t] for t in range(n))]
        if not common:
            return _infeasible(r, c, d, s)
        totals = [sum(costs[t][k] for t in range(n)) for k in common]
        best = min(totals)
        best_depths = [k for k, val in zip(common, totals) if val == best]
        z0 = best_depths[0]      # common is ascending -> lexicographic min
        return _result_from_columns(
            r, c, d, s, [z0] * n, [list(best_depths) for _ in range(n)], best,
            costs=costs)

    # S >= D-1: every depth difference is allowed, so columns decouple.
    if s >= d - 1:
        canonical_flat: list[int] = []
        optional_flat: list[list[int]] = []
        total = 0
        for t in range(n):
            allowed = [k for k in range(d) if k not in forbidden[t]]
            if not allowed:
                return _infeasible(r, c, d, s)
            best = min(costs[t][k] for k in allowed)
            opts = [k for k in allowed if costs[t][k] == best]
            canonical_flat.append(opts[0])  # ascending -> lexicographic min
            optional_flat.append(opts)
            total += best
        return _result_from_columns(r, c, d, s, canonical_flat, optional_flat,
                                    total, costs=costs)

    # Every cut defined by a (possibly infeasible) labelling has a finite
    # part <= n * depth * COST_MAX: unary objective <= n*COST_MAX and the
    # telescoping difference constants contribute < n*(depth-1)*COST_MAX.
    # A value strictly above that is therefore an "infinite" edge: a cut
    # containing one is dominated whenever any feasible labelling exists.
    inf = n * d * COST_MAX + 1

    # Node layout: source=0, sink=1, then n*(d-1) threshold nodes.
    s_node, t_node = 0, 1
    interior = d - 1

    def v(col: int, k: int) -> int:
        # v(t,0) = source, v(t,d) = sink; k in 1..d-1 maps to a real node.
        if k == 0:
            return s_node
        if k == d:
            return t_node
        return 2 + col * interior + (k - 1)

    net = ISAP(2 + n * interior)

    # Per-column structural and unary edges.
    offset = 0
    for t in range(n):
        col_cost = costs[t]
        # Monotonicity: v_k -> v_{k-1} infinite, k=1..d.
        for k in range(1, d + 1):
            net.add_edge(v(t, k), v(t, k - 1), inf)
        # Unary differences for threshold k=1..d-1.
        offset += col_cost[0]
        for k in range(1, d):
            delta = col_cost[k] - col_cost[k - 1]
            if delta >= 0:
                net.add_edge(v(t, k), t_node, delta)
            else:
                net.add_edge(s_node, v(t, k), -delta)
                offset -= -delta  # = offset += delta
        # Forbidden depths a: edge v_a -> v_{a+1} infinite.
        for a in forbidden[t]:
            net.add_edge(v(t, a), v(t, a + 1), inf)

    # Pairwise slope-limit cross edges for 4-neighbours.
    for i in range(r):
        for j in range(c):
            t = i * c + j
            if j + 1 < c:
                q = t + 1
                for k in range(1, d - s):
                    net.add_edge(v(q, k + s), v(t, k), inf)
                    net.add_edge(v(t, k + s), v(q, k), inf)
            if i + 1 < r:
                q = t + c
                for k in range(1, d - s):
                    net.add_edge(v(q, k + s), v(t, k), inf)
                    net.add_edge(v(t, k + s), v(q, k), inf)

    flow = net.max_flow(s_node, t_node, limit=inf)
    if flow >= inf:
        return _infeasible(r, c, d, s)

    optimal_cost = flow + int(offset)

    # Exact Picard-Queyranne classification of the residual graph:
    #   * the source-reachable set is the canonical (smallest) min cut;
    #   * the nodes that can reach the sink form the sink-forced region
    #     (complement of the largest min cut);
    #   * label a is attainable at column t iff v(t,a) can be source-side
    #     (cannot reach the sink), v(t,a+1) can be sink-side (unreachable
    #     from the source), and the two thresholds are not forced into
    #     the same cut side.  The infinite chain arc v(t,a+1) -> v(t,a)
    #     always keeps residual capacity (flow < inf), so a residual path
    #     v(t,a) ~> v(t,a+1) exists iff both share an SCC.
    from_source = net.reachable_from(s_node)
    to_sink = net.reachable_to(t_node)
    comp = net.residual_scc()

    canonical = [[0] * c for _ in range(r)]
    optional = [[[] for _ in range(c)] for _ in range(r)]
    ambiguous = 0

    for i in range(r):
        for j in range(c):
            t = i * c + j
            # Canonical depth: highest source-reachable threshold.
            z = 0
            for k in range(1, d):
                if from_source[v(t, k)]:
                    z = k
            canonical[i][j] = z

            opts = []
            for a in range(d):
                node_a, node_b = v(t, a), v(t, a + 1)
                can_source = not to_sink[node_a]
                can_sink = not from_source[node_b]
                not_forced = comp[node_a] != comp[node_b]
                if can_source and can_sink and not_forced:
                    opts.append(a)
            optional[i][j] = opts
            if len(opts) != 1:
                ambiguous += 1

    canonical_cost = [
        [costs[i * c + j][canonical[i][j]] for j in range(c)] for i in range(r)
    ]
    return SolveResult(
        status="feasible", rows=r, cols=c, depth=d, s=s,
        optimal_cost=optimal_cost,
        canonical_depth=canonical,
        optional_depths=optional,
        canonical_cost=canonical_cost,
        unique=(ambiguous == 0),
        ambiguous_columns=ambiguous,
    )
