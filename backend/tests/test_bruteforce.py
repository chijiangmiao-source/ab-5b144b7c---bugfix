"""Exhaustive cross-check of the min-cut solver against brute force."""
import itertools
import random
import sys

sys.path.insert(0, ".")
from app.solver import solve, validate_input, ValidationError, COST_MAX


def brute(r, c, d, costs, forbidden, s):
    n = r * c
    allowed = [
        [k for k in range(d) if k not in forbidden[t]]
        for t in range(n)
    ]
    best = None
    best_vecs = []
    def neighbors_ok(vec):
        for i in range(r):
            for j in range(c):
                t = i * c + j
                if j + 1 < c and abs(vec[t] - vec[t + 1]) > s:
                    return False
                if i + 1 < r and abs(vec[t] - vec[t + c]) > s:
                    return False
        return True
    for combo in itertools.product(*[range(len(a)) for a in allowed]):
        vec = [allowed[t][combo[t]] for t in range(n)]
        if not neighbors_ok(vec):
            continue
        val = sum(costs[t][vec[t]] for t in range(n))
        if best is None or val < best:
            best = val
            best_vecs = [tuple(vec)]
        elif val == best:
            best_vecs.append(tuple(vec))
    if best is None:
        return None
    lex = list(min(best_vecs))
    optional = [sorted({vec[t] for vec in best_vecs}) for t in range(n)]
    return best, lex, optional


def random_case(seed):
    random.seed(seed)
    r = random.randint(2, 3)
    c = random.randint(2, 3)
    d = random.randint(2, 5)
    s = random.randint(0, 3)
    hi = random.choice([1, 3, 1000000])
    costs = [[random.randint(0, hi) for _ in range(d)] for _ in range(r * c)]
    forbidden = [set() for _ in range(r * c)]
    # occasionally forbid a few voxels, never all in a column
    for t in range(r * c):
        if random.random() < 0.3:
            k = random.randrange(d)
            forbidden[t].add(k)
    return r, c, d, costs, forbidden, s


def main():
    n_cases = 400
    fails = 0
    for seed in range(n_cases):
        r, c, d, costs, forbidden, s = random_case(seed)
        payload = {
            "rows": r, "cols": c, "depth": d, "s": s,
            "costs": [[list(costs[i * c + j]) for j in range(c)] for i in range(r)],
            "forbidden": [[i, j, k]
                          for i in range(r) for j in range(c)
                          for t in [i * c + j] for k in forbidden[t]],
        }
        try:
            res = solve(payload)
        except Exception as e:
            print(f"seed {seed}: solver raised {type(e).__name__}: {e}")
            fails += 1
            continue
        bf = brute(r, c, d, costs, forbidden, s)
        if bf is None:
            if res.status != "infeasible":
                print(f"seed {seed}: expected infeasible, got {res.status}")
                fails += 1
            continue
        best, lex, optional = bf
        if res.status != "feasible":
            print(f"seed {seed}: expected feasible, solver infeasible")
            fails += 1
            continue
        if res.optimal_cost != best:
            print(f"seed {seed}: cost {res.optimal_cost} != brute {best}")
            fails += 1
        flat_canon = [res.canonical_depth[i][j]
                      for i in range(r) for j in range(c)]
        if flat_canon != lex:
            print(f"seed {seed}: canonical {flat_canon} != lex-min {lex}")
            fails += 1
        flat_opt = [res.optional_depths[i][j]
                    for i in range(r) for j in range(c)]
        if flat_opt != optional:
            for t in range(r * c):
                if flat_opt[t] != optional[t]:
                    i, j = divmod(t, c)
                    print(f"seed {seed}: optional[{i},{j}] {flat_opt[t]} != brute {optional[t]}")
            fails += 1
    print(f"{n_cases - fails}/{n_cases} cases matched brute force")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
