// All solving goes through the real FastAPI service. In dev Vite proxies
// /api and /health to the backend; in Docker nginx does the same, so a
// relative base works in both environments.
const BASE = import.meta.env.VITE_API_BASE ?? "";

export async function fetchHealth() {
  const r = await fetch(`${BASE}/health`);
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}

export async function solve(payload) {
  const r = await fetch(`${BASE}/api/solve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  let body = null;
  try {
    body = await r.json();
  } catch {
    body = null;
  }
  if (!r.ok) {
    const err = new Error(body?.message || `服务返回 ${r.status}`);
    err.status = r.status;
    err.code = body?.error || "error";
    err.detail = body?.errors || [];
    throw err;
  }
  return body;
}
