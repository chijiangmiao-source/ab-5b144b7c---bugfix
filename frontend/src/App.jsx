import React, { useEffect, useMemo, useRef, useState } from "react";
import { solve, fetchHealth } from "./api.js";
import { syntheticProblem, ambiguousProblem, infeasibleProblem } from "./samples.js";
import SliceView from "./components/SliceView.jsx";
import TopView from "./components/TopView.jsx";
import ColumnDetail from "./components/ColumnDetail.jsx";

function pretty(obj) {
  return JSON.stringify(obj, null, 2);
}

function tryParse(text) {
  try {
    const obj = JSON.parse(text);
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
      return { ok: false, obj: null, error: "根节点必须是 JSON 对象" };
    }
    return { ok: true, obj, error: null };
  } catch (e) {
    return { ok: false, obj: null, error: `JSON 语法错误：${e.message}` };
  }
}

const initial = syntheticProblem({ rows: 6, cols: 8, depth: 16, s: 2, snrGap: true });

export default function App() {
  const [text, setText] = useState(() => pretty(initial));
  const [result, setResult] = useState(null);
  const [apiErrors, setApiErrors] = useState(null);
  const [loading, setLoading] = useState(false);
  const [stale, setStale] = useState(false);
  const [selectedRow, setSelectedRow] = useState(0);
  const [selected, setSelected] = useState([0, 0]);
  const [forbidMode, setForbidMode] = useState(false);
  const [health, setHealth] = useState("checking");
  const solvedTextRef = useRef("");

  const parsed = useMemo(() => tryParse(text), [text]);
  const obj = parsed.obj;

  useEffect(() => {
    let alive = true;
    const ping = () =>
      fetchHealth()
        .then(() => alive && setHealth("ok"))
        .catch(() => alive && setHealth("down"));
    ping();
    const id = setInterval(ping, 10_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const rows = obj?.rows ?? 0;
  const cols = obj?.cols ?? 0;
  const depth = obj?.depth ?? 0;

  useEffect(() => {
    setSelectedRow((r) => (result && r < result.rows ? r : 0));
  }, [result]);

  function markChanged(nextText) {
    setText(nextText);
    setApiErrors(null);
    if (solvedTextRef.current && nextText !== solvedTextRef.current) setStale(true);
  }

  function updateParam(key, value) {
    if (!parsed.ok) return;
    const next = { ...obj, [key]: value };
    markChanged(pretty(next));
  }

  function loadSample(builder) {
    const p = builder();
    markChanged(pretty(p));
    setResult(null);
    setSelected([0, 0]);
    setSelectedRow(0);
  }

  function toggleForbidden(i, j, k) {
    if (!parsed.ok) return;
    const list = Array.isArray(obj.forbidden) ? obj.forbidden.map((x) => [...x]) : [];
    const idx = list.findIndex(([a, b, c]) => a === i && b === j && c === k);
    if (idx >= 0) list.splice(idx, 1);
    else list.push([i, j, k]);
    markChanged(pretty({ ...obj, forbidden: list }));
  }

  async function onSolve() {
    setApiErrors(null);
    if (!parsed.ok) {
      setResult(null);
      setApiErrors({ code: "local_parse", message: "草稿无法解析", errors: [parsed.error] });
      return;
    }
    setLoading(true);
    try {
      const body = await solve(obj);
      setResult(body);
      solvedTextRef.current = text;
      setStale(false);
      const [sr, sc] = selected;
      setSelectedRow(Math.min(sr, body.rows - 1));
      setSelected([Math.min(sr, body.rows - 1), Math.min(sc, body.cols - 1)]);
    } catch (e) {
      // Input rejected: keep the draft exactly as typed and locate causes.
      setResult(null);
      if (e.status === 422 || e.status === 400 || e.status === 413) {
        setApiErrors({ code: e.code, message: e.message, errors: e.detail });
      } else {
        setApiErrors({
          code: "network",
          message: "无法连接求解服务",
          errors: [e.message || "网络错误，服务可能未启动；草稿已保留"],
        });
      }
    } finally {
      setLoading(false);
    }
  }

  const feasible = result?.status === "feasible";

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>OCT 规范表面审计台</h1>
          <p className="subtitle">
            精确整数最小割 · 行主序字典序规范解 · 逐列完整可选深度集合 · 全程可重算
          </p>
        </div>
        <div className={`health health-${health}`}>
          求解服务：{health === "ok" ? "在线" : health === "checking" ? "检测中…" : "不可达"}
        </div>
      </header>

      <div className="layout">
        <section className="panel editor">
          <div className="panel-head">
            <h2>1. 代价体与参数（草稿）</h2>
            <div className="btn-row">
              <button onClick={() => loadSample(() => syntheticProblem({ snrGap: true }))}>
                低信噪示例
              </button>
              <button onClick={() => loadSample(ambiguousProblem)}>多解示例</button>
              <button onClick={() => loadSample(infeasibleProblem)}>不可行示例</button>
            </div>
          </div>

          <div className="params">
            <label>
              行数 rows (2–40)
              <input
                type="number" min={2} max={40}
                value={Number.isFinite(rows) ? rows : ""}
                disabled={!parsed.ok}
                onChange={(e) => updateParam("rows", Number(e.target.value))}
              />
            </label>
            <label>
              列数 cols (2–40)
              <input
                type="number" min={2} max={40}
                value={Number.isFinite(cols) ? cols : ""}
                disabled={!parsed.ok}
                onChange={(e) => updateParam("cols", Number(e.target.value))}
              />
            </label>
            <label>
              深度 depth (2–64)
              <input
                type="number" min={2} max={64}
                value={Number.isFinite(depth) ? depth : ""}
                disabled={!parsed.ok}
                onChange={(e) => updateParam("depth", Number(e.target.value))}
              />
            </label>
            <label>
              四邻深度差 S (≥0)
              <input
                type="number" min={0}
                value={obj && Number.isFinite(obj.s) ? obj.s : ""}
                disabled={!parsed.ok}
                onChange={(e) => updateParam("s", Number(e.target.value))}
              />
            </label>
          </div>

          <p className="hint">
            可直接粘贴 JSON：三维数组 <code>costs[row][col][depth]</code>，或行主序一维
            整数数组（长度 rows×cols×depth）；禁用体素写在 <code>forbidden</code> 的
            <code> [row, col, depth] </code>三元组中。代价值为 0–1000000 的整数。
          </p>

          <textarea
            className="json-editor"
            spellCheck={false}
            value={text}
            onChange={(e) => markChanged(e.target.value)}
            placeholder='{"rows":2,"cols":2,"depth":2,"s":1,"costs":[[[0,1],[1,0]],[[1,0],[0,1]]]}'
          />

          <div className="solve-row">
            <button className="primary" onClick={onSolve} disabled={loading}>
              {loading ? "精确求解中…" : "提交求解（精确整数）"}
            </button>
            {parsed.ok ? (
              <span className="parse-ok">JSON 语法正确</span>
            ) : (
              <span className="parse-bad">草稿存在语法错误（仍已保留）</span>
            )}
          </div>

          {apiErrors && (
            <div className="errors">
              <h3>{apiErrors.message || "请求被拒绝"}</h3>
              <ul>
                {(apiErrors.errors || []).map((m, i) => (
                  <li key={i}>{m}</li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className="panel results">
          <div className="panel-head">
            <h2>2. 规范表面与歧义范围</h2>
            <div className="btn-row">
              <label className="check">
                <input
                  type="checkbox"
                  checked={forbidMode}
                  onChange={(e) => setForbidMode(e.target.checked)}
                  disabled={!parsed.ok}
                />
                禁用编辑模式（点切片深度切换禁用体素）
              </label>
            </div>
          </div>

          {!result && !apiErrors && (
            <div className="placeholder">提交后在此显示切片、俯视图与逐列审计信息。</div>
          )}

          {result && result.status === "infeasible" && (
            <div className="banner infeasible">
              <h3>无可行表面</h3>
              <p>
                在 rows={result.rows}, cols={result.cols}, depth={result.depth}, S={result.s}
                的约束下不存在满足「每列一个深度、四邻深度差 ≤ S、避开禁用体素」的表面。
                请检查禁用集合或放宽 S。草稿已保留。
              </p>
            </div>
          )}

          {stale && feasible && (
            <div className="banner stale">草稿在上次求解后被修改，以下结果可能已过期，请重新求解。</div>
          )}

          {feasible && (
            <>
              <div className={`summary ${result.unique ? "unique" : "ambiguous"}`}>
                <div>
                  <span className="k">最小总代价（精确整数）</span>
                  <span className="v">{result.optimal_cost.toLocaleString()}</span>
                </div>
                <div>
                  <span className="k">解的性质</span>
                  <span className="v">
                    {result.unique ? "唯一最优表面" : "存在多个最优表面"}
                  </span>
                </div>
                <div>
                  <span className="k">歧义列数</span>
                  <span className="v">
                    {result.ambiguous_columns} / {result.rows * result.cols}
                  </span>
                </div>
                <div>
                  <span className="k">求解耗时</span>
                  <span className="v">{result.elapsed_ms} ms</span>
                </div>
              </div>

              <div className="view-row">
                <div className="view-block">
                  <div className="view-head">
                    <h3>切片（行 {selectedRow}）</h3>
                    <select
                      value={selectedRow}
                      onChange={(e) => {
                        const r = Number(e.target.value);
                        setSelectedRow(r);
                        setSelected([r, selected[1]]);
                      }}
                    >
                      {Array.from({ length: result.rows }, (_, i) => (
                        <option key={i} value={i}>第 {i} 行</option>
                      ))}
                    </select>
                  </div>
                  <SliceView
                    result={result}
                    row={selectedRow}
                    costsObj={parsed.ok ? obj : null}
                    selectedCol={selected[1]}
                    forbidMode={forbidMode}
                    onPick={(j, k) => {
                      const i = selectedRow;
                      if (forbidMode && k != null) toggleForbidden(i, j, k);
                      setSelected([i, j]);
                    }}
                  />
                </div>

                <div className="view-block">
                  <div className="view-head"><h3>俯视图（规范深度）</h3></div>
                  <TopView
                    result={result}
                    selected={selected}
                    onPick={(i, j) => {
                      setSelected([i, j]);
                      setSelectedRow(i);
                    }}
                  />
                </div>
              </div>

              <ColumnDetail
                result={result}
                costsObj={parsed.ok ? obj : null}
                selected={selected}
              />
            </>
          )}
        </section>
      </div>

      <footer className="foot">
        算法：单调链整数 s-t 最小割 + 手写 ISAP 最大流（不使用通用优化求解器）；
        同优时取行主序深度向量的字典序最小；可选深度集合由残量网络 SCC 精确给出。
      </footer>
    </div>
  );
}
