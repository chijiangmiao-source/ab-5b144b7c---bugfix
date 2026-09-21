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
  6. invalid input is rejected with located causes;
  7. flat row-major costs are accepted;
  8. a maximum-size (40x40x64) request with 102 400 integers is accepted.

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
