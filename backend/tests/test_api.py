"""API-level tests through FastAPI's TestClient."""
import sys
sys.path.insert(0, ".")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_limits():
    r = client.get("/api/limits")
    assert r.status_code == 200
    assert r.json()["rows"]["max"] == 40


def payload_2x2():
    # Two rows, two cols, depth 3, s large enough for freedom.
    return {
        "rows": 2, "cols": 2, "depth": 3, "s": 5,
        "costs": [
            [[0, 5, 9], [7, 1, 8]],
            [[3, 0, 2], [4, 4, 0]],
        ],
    }


def test_solve_unique_columns():
    r = client.post("/api/solve", json=payload_2x2())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "feasible"
    assert body["optimal_cost"] == 1  # 0 + 1 + 0 + 0
    assert body["canonical_depth"] == [[0, 1], [1, 2]]
    assert body["canonical_cost"] == [[0, 1], [0, 0]]
    assert body["unique"] is True
    assert body["ambiguous_columns"] == 0
    assert "elapsed_ms" in body


def test_ties_report_multiple_depths():
    p = {
        "rows": 2, "cols": 2, "depth": 2, "s": 1,
        "costs": [
            [[0, 0], [0, 0]],
            [[0, 0], [0, 0]],
        ],
    }
    r = client.post("/api/solve", json=p)
    body = r.json()
    assert body["status"] == "feasible"
    assert body["optimal_cost"] == 0
    assert body["unique"] is False
    assert body["ambiguous_columns"] == 4
    assert body["canonical_depth"] == [[0, 0], [0, 0]]  # lexicographic min
    for i in range(2):
        for j in range(2):
            assert body["optional_depths"][i][j] == [0, 1]


def test_infeasible_forbidden_column():
    p = {
        "rows": 2, "cols": 2, "depth": 2, "s": 5,
        "costs": [[[1, 2], [3, 4]], [[5, 6], [7, 8]]],
        "forbidden": [[0, 0, 0], [0, 0, 1]],
    }
    r = client.post("/api/solve", json=p)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "infeasible"
    assert body["optimal_cost"] is None


def test_infeasible_slope_s_zero():
    # s=0 forces a global depth; forbid depth 0 in one column and depth 1
    # in another -> no common depth remains.
    p = {
        "rows": 2, "cols": 2, "depth": 2, "s": 0,
        "costs": [[[0, 9], [0, 9]], [[9, 0], [9, 0]]],
        "forbidden": [[0, 0, 0], [1, 1, 1]],
    }
    r = client.post("/api/solve", json=p)
    body = r.json()
    assert body["status"] == "infeasible"


def test_validation_locates_causes_and_preserves_shape():
    # Bad dimensions are reported independently...
    r = client.post("/api/solve", json={
        "rows": 1, "cols": 2, "depth": 70, "s": -1,
        "costs": "nope",
    })
    assert r.status_code == 422
    errs = " ".join(r.json()["errors"])
    assert "rows" in errs
    assert "depth" in errs
    assert "s=-1" in errs

    # ...while structurally located forbidden/cost errors fire when the
    # dimensions themselves are valid.
    r2 = client.post("/api/solve", json={
        "rows": 2, "cols": 2, "depth": 2, "s": 1,
        "costs": [[[0, 1], [0, 1]], [[0, 1]]],
        "forbidden": [[5, 0, 0], [0, 0]],
    })
    assert r2.status_code == 422
    errs2 = " ".join(r2.json()["errors"])
    assert "forbidden[0]" in errs2
    assert "forbidden[1]" in errs2
    assert "costs[1]" in errs2


def test_invalid_json():
    r = client.post("/api/solve", content=b"{not json",
                    headers={"content-type": "application/json"})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_json"


def test_flat_cost_vector_accepted():
    p = {
        "rows": 2, "cols": 2, "depth": 2, "s": 1,
        "costs": [0, 9, 9, 0, 0, 9, 9, 0],
    }
    r = client.post("/api/solve", json=p)
    assert r.status_code == 200
    body = r.json()
    assert body["optimal_cost"] == 0
    assert body["canonical_depth"] == [[0, 1], [0, 1]]


def test_cost_range_enforced():
    p = {"rows": 2, "cols": 2, "depth": 2, "s": 1,
         "costs": [[[0, 1_000_001], [0, 0]], [[0, 0], [0, 0]]]}
    r = client.post("/api/solve", json=p)
    assert r.status_code == 422
    assert "1000000" in " ".join(r.json()["errors"])
