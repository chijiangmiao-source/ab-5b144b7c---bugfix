"""Acceptance tests for forbidden-voxel handling and optional-depth sets.

Drives the public ``POST /api/solve`` API (FastAPI TestClient) with
uniform-cost volumes that contain scattered forbidden voxels, then checks:

* exact total cost, canonical surface, per-column optional-depth sets and
  the uniqueness fields for the reference 4x4x10 instance;
* every reported optional depth is witnessed by an optimal surface:
  pinning the column to that depth (forbidding all its other depths) and
  re-solving must keep the same optimal cost -- and pinning any
  non-optional depth must not;
* the canonical surface is the row-major lexicographic minimum: with the
  row-major prefix pinned to the canonical depths, the next column's
  smallest optional depth equals its canonical depth;
* the same invariants on further uniform-cost volumes with slightly
  different sizes/depths/slopes and scattered forbidden positions, so the
  fix is not tailored to a single matrix.
"""
import sys

sys.path.insert(0, ".")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# Reference instance from the audit report: uniform zero costs, s=1, six
# forbidden voxels.  16 columns x 10 depths = 160 flat costs.
MAIN_CASE = {
    "rows": 4, "cols": 4, "depth": 10, "s": 1,
    "costs": [0] * 160,
    "forbidden": [[0, 0, 4], [0, 0, 5], [1, 1, 0], [1, 1, 9],
                  [2, 2, 3], [3, 3, 7]],
}

MAIN_CANONICAL = [[0, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]

_MAIN_FULL = list(range(10))
MAIN_OPTIONAL = {
    (0, 0): [0, 1, 2, 3, 6, 7, 8, 9],
    (1, 1): [1, 2, 3, 4, 5, 6, 7, 8],
    (2, 2): [0, 1, 2, 4, 5, 6, 7, 8, 9],
    (3, 3): [0, 1, 2, 3, 4, 5, 6, 8, 9],
}


def main_expected_optional(i, j):
    return MAIN_OPTIONAL.get((i, j), _MAIN_FULL)


# More uniform-cost volumes: sizes/depths/slopes vary, forbidden voxels
# are scattered across rows, columns and depths.
VARIANTS = [
    {
        "rows": 5, "cols": 3, "depth": 12, "s": 2,
        "costs": [0] * (5 * 3 * 12),
        "forbidden": [[0, 1, 0], [1, 0, 11], [2, 2, 5], [3, 1, 3],
                      [4, 0, 8], [4, 2, 2], [0, 0, 6]],
    },
    {
        "rows": 3, "cols": 5, "depth": 9, "s": 1,
        "costs": [0] * (3 * 5 * 9),
        "forbidden": [[0, 0, 8], [0, 4, 0], [1, 2, 4], [2, 1, 6],
                      [2, 3, 2], [1, 0, 5]],
    },
    {
        "rows": 4, "cols": 4, "depth": 11, "s": 3,
        "costs": [0] * (4 * 4 * 11),
        "forbidden": [[0, 3, 10], [1, 1, 1], [2, 0, 7], [3, 2, 4],
                      [3, 3, 0], [0, 0, 5]],
    },
    {
        # Non-zero uniform cost: optimum is rows*cols*7, not 0.
        "rows": 4, "cols": 3, "depth": 8, "s": 1,
        "costs": [7] * (4 * 3 * 8),
        "forbidden": [[0, 0, 0], [1, 1, 3], [2, 2, 7], [3, 0, 5]],
    },
]


def solve(payload):
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def pinned_payload(payload, fixed):
    """Copy of ``payload`` with each column ``(i, j) -> a`` in ``fixed``
    pinned to depth ``a`` by forbidding every other depth of that column."""
    p = dict(payload)
    d = payload["depth"]
    forb = {tuple(t) for t in payload.get("forbidden", [])}
    for (i, j), a in fixed.items():
        assert 0 <= a < d
        forb |= {(i, j, k) for k in range(d) if k != a}
    p["forbidden"] = [list(t) for t in sorted(forb)]
    return p


def check_uniform_instance_invariants(payload):
    """All invariants that must hold for a feasible uniform-cost volume."""
    r, c, d = payload["rows"], payload["cols"], payload["depth"]
    forbidden = {(i, j, k) for i, j, k in payload.get("forbidden", [])}
    uniform = payload["costs"][0]
    assert all(v == uniform for v in payload["costs"])

    body = solve(payload)
    assert body["status"] == "feasible"
    assert body["optimal_cost"] == uniform * r * c
    opt_cost = body["optimal_cost"]
    canon = body["canonical_depth"]
    optional = body["optional_depths"]

    # Structural invariants: canonical depth is optional, nothing
    # forbidden is canonical or optional, uniqueness flags agree.
    n_ambiguous = 0
    for i in range(r):
        for j in range(c):
            opts = optional[i][j]
            assert opts, f"({i},{j}): optional set must not be empty"
            assert canon[i][j] in opts, f"({i},{j}): canonical not optional"
            assert (i, j, canon[i][j]) not in forbidden
            assert not {(i, j, k) for k in opts} & forbidden, (
                f"({i},{j}): forbidden depth listed as optional")
            if len(opts) != 1:
                n_ambiguous += 1
    assert body["ambiguous_columns"] == n_ambiguous
    assert body["unique"] == (n_ambiguous == 0)

    # Witness property, both directions: depth a is listed as optional at
    # (i, j) iff pinning that column to a still allows an optimal-cost
    # surface.  This re-solves the instance r*c*d times with one extra
    # temporary constraint each.
    for i in range(r):
        for j in range(c):
            for a in range(d):
                sub = solve(pinned_payload(payload, {(i, j): a}))
                attainable = (sub["status"] == "feasible"
                              and sub["optimal_cost"] == opt_cost)
                assert attainable == (a in optional[i][j]), (
                    f"({i},{j}) depth {a}: optional={a in optional[i][j]} "
                    f"but pinned solve gives status={sub['status']} "
                    f"cost={sub['optimal_cost']} (optimum {opt_cost})")

    # Lexicographic-minimum property: pin the row-major prefix to the
    # canonical depths; the next column's smallest optional depth must be
    # exactly its canonical depth.
    for t in range(r * c):
        i, j = divmod(t, c)
        prefix = {(ii, jj): canon[ii][jj]
                  for ii, jj in (divmod(u, c) for u in range(t))}
        sub = solve(pinned_payload(payload, prefix))
        assert sub["status"] == "feasible"
        assert sub["optimal_cost"] == opt_cost
        assert min(sub["optional_depths"][i][j]) == canon[i][j], (
            f"prefix up to ({i},{j}): canonical {canon[i][j]} is not the "
            f"smallest attainable depth {sub['optional_depths'][i][j]}")

    return body


def test_reference_case_exact_values():
    """The reported 4x4x10 instance must reproduce the audited values."""
    body = solve(MAIN_CASE)
    assert body["status"] == "feasible"
    assert body["optimal_cost"] == 0
    assert body["canonical_depth"] == MAIN_CANONICAL
    assert body["canonical_cost"] == [[0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            assert body["optional_depths"][i][j] == main_expected_optional(i, j), (
                f"optional[{i}][{j}] = {body['optional_depths'][i][j]}")
    assert body["unique"] is False
    assert body["ambiguous_columns"] == 16


def test_reference_case_invariants():
    check_uniform_instance_invariants(MAIN_CASE)


def test_uniform_variants_invariants():
    for payload in VARIANTS:
        body = check_uniform_instance_invariants(payload)
        # Uniform costs with only scattered forbidden voxels always leave
        # room for more than one optimal surface.
        assert body["unique"] is False
        assert body["ambiguous_columns"] > 0
