"""FastAPI application: exact-integer OCT surface solver audit API."""

from __future__ import annotations

import os
import time
from dataclasses import asdict

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .solver import solve, ValidationError

app = FastAPI(
    title="OCT 规范表面审计 API",
    version="1.0.0",
    description="精确整数最小割求解：规范表面、最优总代价与逐列可选深度集合。",
)

_origins_env = os.environ.get("CORS_ORIGINS", "*").strip()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[p.strip() for p in _origins_env.split(",")] if _origins_env else [],
    allow_origin_regex=r".*" if _origins_env == "*" else None,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Largest legal payload (rows*cols*depth integers).  Reject absurd bodies
# before JSON parsing ties up the worker; the audit tool maxes at 102 400.
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", 32 * 1024 * 1024))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "oct-surface-audit", "version": app.version}


@app.get("/api/limits")
async def limits() -> dict:
    return {
        "rows": {"min": 2, "max": 40},
        "cols": {"min": 2, "max": 40},
        "depth": {"min": 2, "max": 64},
        "cost": {"min": 0, "max": 1_000_000},
        "s": {"min": 0},
        "max_columns": 40 * 40,
    }


@app.exception_handler(ValidationError)
async def validation_error_handler(_request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "invalid_input",
            "message": "输入不合法",
            "errors": exc.errors,
        },
    )


@app.post("/api/solve")
async def solve_endpoint(request: Request) -> JSONResponse:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content={
                "error": "payload_too_large",
                "message": f"请求体超过 {MAX_BODY_BYTES} 字节上限",
                "errors": [f"请求体大小 {len(raw)} 字节超过上限 {MAX_BODY_BYTES}"],
            },
        )
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_json",
                "message": "请求体不是合法 JSON",
                "errors": ["无法解析请求体：请粘贴合法的 JSON 文本"],
            },
        )
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_input",
                "message": "输入不合法",
                "errors": ["请求体必须是 JSON 对象，例如 {\"rows\":.., \"costs\":..}"],
            },
        )

    started = time.perf_counter()
    # Exact solve is CPU-bound (worst case tens of seconds at max size);
    # run it in the worker threadpool so /health stays responsive.
    result = await run_in_threadpool(solve, payload)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    body = asdict(result)
    body["elapsed_ms"] = elapsed_ms
    body["algorithm"] = "exact-integer-mincut-isap"
    return JSONResponse(status_code=200, content=body)
