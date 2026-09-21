#!/usr/bin/env python3
"""
End-to-end acceptance for the OCT surface audit stack.

Runs entirely over HTTP against the running compose services:

* http://web        -> nginx static SPA + reverse proxy
* http://api:8000   -> FastAPI exact solver

Checks:
  1. api /health and web /healthz;
  2. the SPA document is served by the web tier;
  3. a small solve through the WEB tier (nginx -> FastAPI) is exactly
     right, independently confirmed by an exhaustive brute force;
  4. tie handling (canonical lexicographic minimum + optional depths);
  5. infeasible problem reporting;
  6. the reported all-zero 4x4x10 volume: exact canonical surface, exact
     per-column optional sets, uniqueness fields, and a pinned re-solve of
     every depth confirming each optional depth is realisable at cost 0
     and every other depth is infeasible;
  7. the same invariants on varied all-zero volumes (different sizes,
     depths, slopes, scattered forbidden voxels);
  8. invalid input is rejected with located causes;
  9. flat row-major costs are accepted;
  10. a maximum-size (40x40x64) request with 102 400 integers is accepted.

Exits 0 only if every check passes; prints one FAIL line per failure.
"""

from __future__ import annotations

import itertools
import json
import os
import sys
import time
import urllib.error
import urllib.request

WEB = os.environ.get("WEB_URL", "http://web")
API = os.environ.get("API_URL", "http://api:8000")

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" -- {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(f"{name}: {detail}")


def wait_url(url: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status == 200:
                    return True
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            time.sleep(1.0)
    print(f"  (waited {timeout}s for {url}: {last})")
    return False


def post_json(url: str, payload: dict, timeout: float = 120.0):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"content-type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def get(url: str, timeout: float = 10.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.status, resp.read().decode()


def brute_force(r, c, d, costs, forbidden, s):
    """Independent exhaustive optimum + per-column attainable depths."""
    n = r * c
    allowed = [
        [k for k in range(d) if k not in forbidden[t]]
        for t in range(n)
    ]

    def ok(vec):
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
        if not ok(vec):
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


def main() -> int:
    print("== service health ==")
    check("api /health reachable", wait_url(f"{API}/health"))
    check("web /healthz reachable", wait_url(f"{WEB}/healthz"))

    print("\n== SPA served by web tier ==")
    try:
        status, html = get(f"{WEB}/")
        check("web returns SPA document", status == 200 and 'id="root"' in html,
              f"status={status}")
    except Exception as exc:  # noqa: BLE001
        check("web returns SPA document", False, repr(exc))

    # ---- Small instance, independently brute-forced ---------------------
    r, c, d, s = 3, 3, 4, 1
    nested = [
        [[3, 0, 4, 9], [8, 1, 2, 7], [5, 5, 0, 3]],
        [[2, 0, 6, 8], [9, 9, 0, 1], [4, 2, 1, 0]],
        [[1, 3, 0, 7], [6, 0, 2, 2], [0, 4, 5, 1]],
    ]
    flat = [nested[i][j][k] for i in range(r) for j in range(c) for k in range(d)]
    payload = {"rows": r, "cols": c, "depth": d, "s": s, "costs": nested}
    costs = [list(nested[i][j]) for i in range(r) for j in range(c)]

    print("\n== solve via WEB tier (nginx -> FastAPI) ==")
    status, body = post_json(f"{WEB}/api/solve", payload)
    check("web proxies solve with 200", status == 200, f"status={status} body={body}")
    first_result = body
    if status == 200:
        bf_cost, bf_lex, bf_opts = brute_force(r, c, d, costs, [set() for _ in range(r*c)], s)
        got_lex = [body["canonical_depth"][i][j]
                   for i in range(r) for j in range(c)]
        got_opts = [body["optional_depths"][i][j]
                    for i in range(r) for j in range(c)]
        check("optimal cost matches brute force",
              body["optimal_cost"] == bf_cost,
              f"{body['optimal_cost']} != {bf_cost}")
        check("canonical vector is lexicographic minimum",
              got_lex == bf_lex, f"{got_lex} != {bf_lex}")
        check("optional depth sets match brute force",
              got_opts == bf_opts, f"{got_opts} != {bf_opts}")
        check("canonical costs reported",
              body["canonical_cost"][0][0] == nested[0][0][got_lex[0]])
        check("integer-typed cost",
              isinstance(body["optimal_cost"], int))

    # ---- All-tied ambiguity ---------------------------------------------
    print("\n== multiple optima ==")
    tie = {"rows": 2, "cols": 2, "depth": 2, "s": 1,
           "costs": [[[0, 0], [0, 0]], [[0, 0], [0, 0]]]}
    status, body = post_json(f"{API}/api/solve", tie)
    check("tie case feasible", status == 200 and body["status"] == "feasible")
    check("tie case non-unique", body.get("unique") is False
          and body.get("ambiguous_columns") == 4)
    check("tie canonical is all-zero (lexicographic min)",
          body.get("canonical_depth") == [[0, 0], [0, 0]])
    check("tie optional depths complete",
          all(body["optional_depths"][i][j] == [0, 1]
              for i in range(2) for j in range(2)))

    # ---- Infeasible ------------------------------------------------------
    print("\n== infeasible surface ==")
    infp = {"rows": 2, "cols": 2, "depth": 3, "s": 0,
            "costs": [[[0, 9, 9], [9, 0, 9]], [[9, 9, 0], [0, 9, 9]]],
            "forbidden": [[0, 1, 0], [1, 0, 1], [0, 0, 2]]}
    status, body = post_json(f"{API}/api/solve", infp)
    check("infeasible reported with 200",
          status == 200 and body.get("status") == "infeasible",
          f"status={status} body={body}")
    check("infeasible has no cost/surface",
          body.get("optimal_cost") is None and body.get("canonical_depth") is None)

    # ---- Reported all-zero 4x4x10 volume ---------------------------------
    # Regression: every feasible surface is optimal here; the canonical
    # surface must be the row-major lexicographic minimum and each column's
    # optional set must list exactly the depths some optimal surface uses.
    print("\n== all-zero 4x4x10 volume with scattered forbidden voxels ==")
    zforb = [[0, 0, 4], [0, 0, 5], [1, 1, 0], [1, 1, 9], [2, 2, 3], [3, 3, 7]]
    zero = {"rows": 4, "cols": 4, "depth": 10, "s": 1,
            "costs": [0] * (4 * 4 * 10), "forbidden": zforb}
    exp_canon = [[0, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    exp_opts = [[list(range(10)) for _ in range(4)] for _ in range(4)]
    exp_opts[0][0] = [0, 1, 2, 3, 6, 7, 8, 9]
    exp_opts[1][1] = [1, 2, 3, 4, 5, 6, 7, 8]
    exp_opts[2][2] = [0, 1, 2, 4, 5, 6, 7, 8, 9]
    exp_opts[3][3] = [0, 1, 2, 3, 4, 5, 6, 8, 9]
    status, body = post_json(f"{API}/api/solve", zero)
    check("zero volume feasible with cost 0",
          status == 200 and body.get("status") == "feasible"
          and body.get("optimal_cost") == 0,
          f"status={status} body={str(body)[:200]}")
    if status == 200 and body.get("status") == "feasible":
        check("zero volume canonical is lexicographic min",
              body["canonical_depth"] == exp_canon,
              str(body["canonical_depth"]))
        check("zero volume optional sets exact",
              body["optional_depths"] == exp_opts,
              str(body["optional_depths"]))
        check("zero volume non-unique with 16 ambiguous columns",
              body["unique"] is False and body["ambiguous_columns"] == 16,
              f"unique={body.get('unique')} ambiguous={body.get('ambiguous_columns')}")
        check("zero volume canonical depths are optional and not forbidden",
              all(body["canonical_depth"][i][j] in body["optional_depths"][i][j]
                  and [i, j, body["canonical_depth"][i][j]] not in zforb
                  for i in range(4) for j in range(4)))
        check("zero volume optional sets contain no forbidden voxel",
              all(k not in body["optional_depths"][i][j] for i, j, k in zforb))

        # Pin every column to every depth in turn (temporary extra forbidden
        # voxels): optional depths must stay feasible at total cost 0 with
        # the pinned depth selected; every other depth must be infeasible.
        pin_failures = []
        for i in range(4):
            for j in range(4):
                for a in range(10):
                    pin = dict(zero)
                    pin["forbidden"] = zforb + [
                        [i, j, k] for k in range(10)
                        if k != a and [i, j, k] not in zforb
                    ]
                    st2, b2 = post_json(f"{API}/api/solve", pin)
                    if a in exp_opts[i][j]:
                        ok = (st2 == 200 and b2.get("status") == "feasible"
                              and b2.get("optimal_cost") == 0
                              and b2["canonical_depth"][i][j] == a)
                    else:
                        ok = st2 == 200 and b2.get("status") == "infeasible"
                    if not ok:
                        pin_failures.append(f"({i},{j}) depth {a}")
        check("pinned re-solve confirms every optional depth",
              not pin_failures, ", ".join(pin_failures[:5]))

    # ---- Varied all-zero volumes ------------------------------------------
    # Same invariants at slightly different sizes/depths/slopes with
    # scattered forbidden voxels, so the fix cannot be instance-specific.
    print("\n== varied all-zero volumes ==")
    varied = [
        {"rows": 3, "cols": 4, "depth": 8, "s": 1,
         "forbidden": [[0, 1, 3], [1, 0, 0], [1, 2, 7], [2, 3, 2], [2, 0, 5],
                       [0, 3, 6]]},
        {"rows": 5, "cols": 3, "depth": 12, "s": 2,
         "forbidden": [[0, 0, 6], [1, 1, 11], [2, 2, 0], [3, 0, 4], [4, 2, 8],
                       [2, 0, 9], [0, 2, 3]]},
        {"rows": 4, "cols": 4, "depth": 6, "s": 3,
         "forbidden": [[0, 3, 5], [3, 0, 0], [1, 2, 2], [2, 1, 4]]},
    ]
    for vi, vp in enumerate(varied):
        vr, vc, vd = vp["rows"], vp["cols"], vp["depth"]
        vp["costs"] = [0] * (vr * vc * vd)
        status, body = post_json(f"{API}/api/solve", vp)
        ok = status == 200 and body.get("status") == "feasible"
        check(f"varied[{vi}] feasible with cost 0",
              ok and body["optimal_cost"] == 0,
              f"status={status} body={str(body)[:200]}")
        if not ok:
            continue
        canon, opts = body["canonical_depth"], body["optional_depths"]
        forb = {tuple(t) for t in vp["forbidden"]}
        inv = all(
            canon[i][j] in opts[i][j]
            and canon[i][j] == min(opts[i][j])
            and (i, j, canon[i][j]) not in forb
            and all((i, j, k) not in forb for k in opts[i][j])
            for i in range(vr) for j in range(vc)
        )
        amb = sum(1 for i in range(vr) for j in range(vc) if len(opts[i][j]) != 1)
        check(f"varied[{vi}] canonical/optional/forbidden invariants", inv)
        check(f"varied[{vi}] uniqueness fields consistent",
              body["ambiguous_columns"] == amb and body["unique"] is (amb == 0))
        pin_bad = []
        for i in range(vr):
            for j in range(vc):
                for a in range(vd):
                    pin = dict(vp)
                    pin["forbidden"] = vp["forbidden"] + [
                        [i, j, k] for k in range(vd)
                        if k != a and (i, j, k) not in forb
                    ]
                    st2, b2 = post_json(f"{API}/api/solve", pin)
                    if a in opts[i][j]:
                        good = (st2 == 200 and b2.get("status") == "feasible"
                                and b2.get("optimal_cost") == 0
                                and b2["canonical_depth"][i][j] == a)
                    else:
                        good = st2 == 200 and b2.get("status") == "infeasible"
                    if not good:
                        pin_bad.append(f"({i},{j}) depth {a}")
        check(f"varied[{vi}] pinned re-solve matches optional sets",
              not pin_bad, ", ".join(pin_bad[:5]))

    # ---- Invalid input with located causes ------------------------------
    print("\n== invalid input ==")
    # Bad dimensions are reported independently first.
    bad = {"rows": 1, "cols": 2, "depth": 90, "s": -2, "costs": []}
    status, body = post_json(f"{API}/api/solve", bad)
    msgs = " ".join(body.get("errors", []))
    check("invalid input -> 422", status == 422, f"status={status}")
    check("errors locate rows/depth/s",
          all(token in msgs for token in ("rows", "depth", "s=-2")),
          msgs)
    # With valid dimensions, out-of-range forbidden coordinates are located
    # by their exact list index.
    bad2 = {"rows": 2, "cols": 2, "depth": 2, "s": 1,
            "costs": [[[0, 1], [0, 1]], [[0, 1], [0, 1]]],
            "forbidden": [[9, 0, 0], [0, 0]]}
    status, body = post_json(f"{API}/api/solve", bad2)
    msgs2 = " ".join(body.get("errors", []))
    check("forbidden errors are located by index", status == 422
          and "forbidden[0]" in msgs2 and "forbidden[1]" in msgs2,
          f"status={status} {msgs2}")

    bad_json_status = None
    req = urllib.request.Request(f"{API}/api/solve", data=b"{oops",
                                 headers={"content-type": "application/json"})
    try:
        urllib.request.urlopen(req)
    except urllib.error.HTTPError as exc:
        bad_json_status = exc.code
    check("malformed JSON -> 400", bad_json_status == 400, f"got {bad_json_status}")

    # ---- Flat row-major cost vector --------------------------------------
    print("\n== flat cost vector ==")
    flatp = {"rows": r, "cols": c, "depth": d, "s": s, "costs": flat}
    status, body2 = post_json(f"{API}/api/solve", flatp)
    check("flat vector accepted and equal",
          status == 200 and body2["optimal_cost"] == first_result["optimal_cost"]
          and body2["canonical_depth"] == first_result["canonical_depth"],
          f"status={status}")

    # ---- Maximum-size request --------------------------------------------
    print("\n== maximum size 40x40x64 ==")
    R = C = 40
    D = 64
    # s=0 forces a single global depth; build flat costs cheaply.
    big = [0] * (R * C * D)
    # make depth 3 uniquely best everywhere, depth 7 forbidden in one col
    for t in range(R * C):
        for k in range(D):
            big[t * D + k] = 10 if k != 3 else 0
    bigp = {"rows": R, "cols": C, "depth": D, "s": 0, "costs": big,
            "forbidden": [[0, 0, 7]]}
    status, body = post_json(f"{WEB}/api/solve", bigp, timeout=60)
    check("max-size request solved via web",
          status == 200 and body["status"] == "feasible",
          f"status={status} body={str(body)[:200]}")
    if status == 200:
        check("max-size cost exact", body["optimal_cost"] == 0,
              str(body["optimal_cost"]))
        check("max-size unique and canonical depth 3",
              body["unique"] is True
              and body["canonical_depth"][39][39] == 3)

    print("\n" + "=" * 60)
    if failures:
        print(f"ACCEPTANCE FAILED: {len(failures)} check(s) failed")
        for f in failures:
            print("  -", f)
        return 1
    print("ALL END-TO-END CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
