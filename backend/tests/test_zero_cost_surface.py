"""Acceptance tests for all-zero cost volumes through the public API.

Regression coverage for the residual-reachability defect that, on
instances whose residual condensation DAG exceeded 128 components,
reported forbidden voxels as canonical depths and emptied every
per-column optional-depth set (all-zero 4x4x10 volume, s=1).

Every request goes through the public ``POST /api/solve`` endpoint.
"""
import itertools
import sys

sys.path.insert(0, ".")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ---- The reported instance -------------------------------------------------
ROWS = COLS = 4
DEPTH = 10
SLOPE = 1
FORBIDDEN = [[0, 0, 4], [0, 0, 5], [1, 1, 0], [1, 1, 9], [2, 2, 3], [3, 3, 7]]

MAIN_PAYLOAD = {
    "rows": ROWS,
    "cols": COLS,
    "depth": DEPTH,
    "s": SLOPE,
    "costs": [0] * (ROWS * COLS * DEPTH),
    "forbidden": FORBIDDEN,
}

EXPECTED_CANONICAL = [
    [0, 0, 0, 0],
    [0, 1, 0, 0],
    [0, 0, 0, 0],
    [0, 0, 0, 0],
]


def _expected_optional():
    grid = [[list(range(DEPTH)) for _ in range(COLS)] for _ in range(ROWS)]
    grid[0][0] = [0, 1, 2, 3, 6, 7, 8, 9]
    grid[1][1] = [1, 2, 3, 4, 5, 6, 7, 8]
    grid[2][2] = [0, 1, 2, 4, 5, 6, 7, 8, 9]
    grid[3][3] = [0, 1, 2, 3, 4, 5, 6, 8, 9]
    return grid


EXPECTED_OPTIONAL = _expected_optional()


def solve(payload):
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def forced_variant(payload, i, j, a):
    """Same volume plus temporary constraints pinning column (i, j) to depth a."""
    existing = {tuple(t) for t in payload.get("forbidden", [])}
    extra = [
        [i, j, k]
        for k in range(payload["depth"])
        if k != a and (i, j, k) not in existing
    ]
    out = dict(payload)
    out["costs"] = list(payload["costs"])
    out["forbidden"] = [list(t) for t in payload.get("forbidden", [])] + extra
    return out


def check_zero_volume_invariants(payload, label):
    """Invariants every all-zero cost volume must satisfy via the public API.

    With identically zero costs every feasible surface is optimal, so a
    depth is optional iff pinning the column to it keeps a feasible
    (necessarily cost-0) surface; any other depth must turn infeasible.
    """
    body = solve(payload)
    r, c, d, s = payload["rows"], payload["cols"], payload["depth"], payload["s"]
    forbidden = {tuple(t) for t in payload.get("forbidden", [])}

    assert body["status"] == "feasible", f"{label}: expected feasible"
    assert body["optimal_cost"] == 0, f"{label}: zero volume must keep cost 0"
    canon = body["canonical_depth"]
    opts = body["optional_depths"]

    ambiguous = 0
    for i in range(r):
        for j in range(c):
            z, o = canon[i][j], opts[i][j]
            assert o, f"{label}: empty optional set at {(i, j)}"
            assert z in o, f"{label}: canonical depth not optional at {(i, j)}"
            assert z == min(o), f"{label}: canonical not lexicographic min at {(i, j)}"
            assert (i, j, z) not in forbidden, f"{label}: forbidden canonical at {(i, j)}"
            assert all((i, j, k) not in forbidden for k in o), (
                f"{label}: forbidden depth listed optional at {(i, j)}"
            )
            if len(o) != 1:
                ambiguous += 1
    # The canonical surface itself must respect the slope limit.
    for i in range(r):
        for j in range(c):
            if j + 1 < c:
                assert abs(canon[i][j] - canon[i][j + 1]) <= s, f"{label}: slope"
            if i + 1 < r:
                assert abs(canon[i][j] - canon[i + 1][j]) <= s, f"{label}: slope"
    assert body["ambiguous_columns"] == ambiguous, f"{label}: ambiguous count"
    assert body["unique"] is (ambiguous == 0), f"{label}: unique flag"

    # Re-solve with each column pinned to each depth: optional depths must
    # remain feasible at total cost 0, every other depth must be impossible.
    for i in range(r):
        for j in range(c):
            for a in range(d):
                forced = solve(forced_variant(payload, i, j, a))
                if a in opts[i][j]:
                    assert forced["status"] == "feasible", (
                        f"{label}: optional depth {a} at {(i, j)} not realisable"
                    )
                    assert forced["optimal_cost"] == 0, (
                        f"{label}: pinned depth {a} at {(i, j)} raised the cost"
                    )
                    assert forced["canonical_depth"][i][j] == a
                else:
                    assert forced["status"] == "infeasible", (
                        f"{label}: non-optional depth {a} at {(i, j)} became feasible"
                    )
    return body


def test_reported_instance_exact_fields():
    body = solve(MAIN_PAYLOAD)
    assert body["status"] == "feasible"
    assert body["optimal_cost"] == 0
    assert body["canonical_depth"] == EXPECTED_CANONICAL
    assert body["optional_depths"] == EXPECTED_OPTIONAL
    assert body["unique"] is False
    assert body["ambiguous_columns"] == 16
    assert body["canonical_cost"] == [[0] * COLS for _ in range(ROWS)]


def test_reported_instance_nested_costs_agree():
    nested = [
        [[0] * DEPTH for _ in range(COLS)] for _ in range(ROWS)
    ]
    body = solve({**MAIN_PAYLOAD, "costs": nested})
    assert body["canonical_depth"] == EXPECTED_CANONICAL
    assert body["optional_depths"] == EXPECTED_OPTIONAL
    assert body["optimal_cost"] == 0


def test_reported_instance_audit_invariants():
    check_zero_volume_invariants(MAIN_PAYLOAD, "reported 4x4x10")


# ---- Same invariants on varied all-zero volumes -----------------------------
# Sizes/depths/slopes differ and forbidden voxels are scattered, so the
# regression cannot be fixed for the single reported matrix only.
VARIED_PAYLOADS = [
    {
        "rows": 3, "cols": 4, "depth": 8, "s": 1,
        "costs": [0] * (3 * 4 * 8),
        "forbidden": [[0, 1, 3], [1, 0, 0], [1, 2, 7], [2, 3, 2], [2, 0, 5], [0, 3, 6]],
    },
    {
        "rows": 5, "cols": 3, "depth": 12, "s": 2,
        "costs": [0] * (5 * 3 * 12),
        "forbidden": [[0, 0, 6], [1, 1, 11], [2, 2, 0], [3, 0, 4], [4, 2, 8],
                      [2, 0, 9], [0, 2, 3]],
    },
    {
        "rows": 4, "cols": 4, "depth": 6, "s": 3,
        "costs": [0] * (4 * 4 * 6),
        "forbidden": [[0, 3, 5], [3, 0, 0], [1, 2, 2], [2, 1, 4]],
    },
    {
        # s = 0 special case: one global depth for the whole grid.
        "rows": 3, "cols": 3, "depth": 5, "s": 0,
        "costs": [0] * (3 * 3 * 5),
        "forbidden": [[0, 0, 1], [1, 1, 2], [2, 2, 4]],
    },
    {
        # s >= depth-1 special case: columns fully decouple.
        "rows": 4, "cols": 3, "depth": 4, "s": 9,
        "costs": [0] * (4 * 3 * 4),
        "forbidden": [[0, 0, 0], [1, 1, 1], [2, 2, 2], [3, 0, 3]],
    },
]


def test_varied_zero_cost_volumes():
    for idx, payload in enumerate(VARIED_PAYLOADS):
        check_zero_volume_invariants(payload, f"varied[{idx}]")


# ---- Independent brute force on a small varied volume -----------------------
def brute_force(r, c, d, costs, forbidden, s):
    """Exhaustive optimum, lexicographic-min surface and attainable depths."""
    n = r * c
    allowed = [[k for k in range(d) if k not in forbidden[t]] for t in range(n)]

    def slope_ok(vec):
        for i in range(r):
            for j in range(c):
                t = i * c + j
                if j + 1 < c and abs(vec[t] - vec[t + 1]) > s:
                    return False
                if i + 1 < r and abs(vec[t] - vec[t + c]) > s:
                    return False
        return True

    best, vecs = None, []
    for combo in itertools.product(*[range(len(a)) for a in allowed]):
        vec = tuple(allowed[t][combo[t]] for t in range(n))
        if not slope_ok(vec):
            continue
        val = sum(costs[t][vec[t]] for t in range(n))
        if best is None or val < best:
            best, vecs = val, [vec]
        elif val == best:
            vecs.append(vec)
    if best is None:
        return None, None, None
    lex = list(min(vecs))
    opts = [sorted({v[t] for v in vecs}) for t in range(n)]
    return best, lex, opts


def test_small_varied_instance_matches_brute_force():
    r, c, d, s = 3, 3, 4, 1
    forbidden_list = [[0, 0, 2], [1, 1, 0], [2, 2, 3], [0, 2, 1], [2, 0, 0]]
    payload = {
        "rows": r, "cols": c, "depth": d, "s": s,
        "costs": [0] * (r * c * d),
        "forbidden": forbidden_list,
    }
    body = solve(payload)
    forbidden = [set() for _ in range(r * c)]
    for i, j, k in forbidden_list:
        forbidden[i * c + j].add(k)
    costs = [[0] * d for _ in range(r * c)]
    best, lex, opts = brute_force(r, c, d, costs, forbidden, s)

    assert body["status"] == "feasible"
    assert body["optimal_cost"] == best == 0
    flat_canon = [body["canonical_depth"][i][j] for i in range(r) for j in range(c)]
    flat_opts = [body["optional_depths"][i][j] for i in range(r) for j in range(c)]
    assert flat_canon == lex
    assert flat_opts == opts
