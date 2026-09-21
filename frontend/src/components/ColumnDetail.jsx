import React, { useMemo } from "react";
import { columnCosts, isForbidden } from "./util.js";

// Audit card for one lateral column: canonical depth vs the complete set
// of depths that occur in some optimal surface, each with its exact cost.
export default function ColumnDetail({ result, costsObj, selected }) {
  const [i, j] = selected;
  const { depth, s } = result;
  const z = result.canonical_depth[i][j];
  const opts = result.optional_depths[i][j];
  const costs = costsObj ? columnCosts(costsObj, i, j) : null;
  const canonCost = result.canonical_cost?.[i]?.[j] ?? costs?.[z] ?? null;

  const neighbors = useMemo(() => {
    const out = [];
    for (const [di, dj, name] of [[-1, 0, "上"], [1, 0, "下"], [0, -1, "左"], [0, 1, "右"]]) {
      const ni = i + di, nj = j + dj;
      if (ni >= 0 && ni < result.rows && nj >= 0 && nj < result.cols) {
        out.push({ name, ni, nj, z: result.canonical_depth[ni][nj] });
      }
    }
    return out;
  }, [i, j, result]);

  const maxCost = costs ? Math.max(...costs, 1) : 1;
  const uniqueHere = opts.length === 1;

  return (
    <div className="detail">
      <div className="detail-head">
        <h3>
          列审计 · 位置 (row={i}, col={j})
        </h3>
        <span className={`tag ${uniqueHere ? "tag-unique" : "tag-amb"}`}>
          {uniqueHere ? "本列深度在所有最优表面中唯一" : `本列有 ${opts.length} 个可选深度`}
        </span>
      </div>

      <div className="detail-grid">
        <div className="kv">
          <span className="k">规范深度（字典序最小）</span>
          <span className="v strong">{z}</span>
        </div>
        <div className="kv">
          <span className="k">规范深度代价</span>
          <span className="v strong">{canonCost?.toLocaleString() ?? "—"}</span>
        </div>
        <div className="kv">
          <span className="k">全局最小总代价</span>
          <span className="v">{result.optimal_cost.toLocaleString()}</span>
        </div>
        <div className="kv">
          <span className="k">可选深度集合</span>
          <span className="v">
            {opts.length ? opts.map((d) => (
              <span key={d} className={`depth-chip ${d === z ? "chip-canon" : ""}`}>{d}</span>
            )) : <em>空</em>}
          </span>
        </div>
      </div>

      {costs ? (
        <div className="cost-bars" aria-label="该列各深度代价">
          {costs.map((cv, k) => {
            const forb = isForbidden(costsObj, i, j, k);
            const opt = opts.includes(k);
            const canon = k === z;
            return (
              <div
                key={k}
                className={`bar-col ${opt ? "bar-opt" : ""} ${canon ? "bar-canon" : ""} ${
                  forb ? "bar-forb" : ""
                }`}
                title={`深度 ${k} · 代价 ${cv}${forb ? " · 禁用" : ""}${
                  canon ? " · 规范" : ""
                }${opt ? " · 可出现在某最优表面" : ""}`}
              >
                <div className="bar" style={{ height: `${(cv / maxCost) * 100}%` }} />
                <span className="bar-k">{k}</span>
                {canon && <span className="bar-flag">★</span>}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="hint">当前草稿不可解析或代价数据缺失，无法显示逐深度代价。</p>
      )}

      <table className="opt-table">
        <thead>
          <tr><th>深度</th><th>代价</th><th>是否禁用</th><th>角色</th></tr>
        </thead>
        <tbody>
          {Array.from({ length: depth }, (_, k) => {
            const forb = costsObj ? isForbidden(costsObj, i, j, k) : false;
            const opt = opts.includes(k);
            return (
              <tr key={k} className={k === z ? "row-canon" : opt ? "row-opt" : ""}>
                <td>{k}</td>
                <td>{costs ? costs[k].toLocaleString() : "—"}</td>
                <td>{forb ? "是（禁止选择）" : "否"}</td>
                <td>
                  {k === z ? "规范深度" : ""}
                  {opt && k !== z ? "可出现在其他最优表面" : ""}
                  {!opt && k !== z ? "不在任何最优表面中" : ""}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="neighbors">
        <h4>四邻约束核对（|Δ深度| ≤ S = {s}）</h4>
        <div className="nbr-row">
          {neighbors.map(({ name, ni, nj, z: nz }) => {
            const ok = Math.abs(nz - z) <= s;
            return (
              <span key={name} className={`nbr ${ok ? "nbr-ok" : "nbr-bad"}`}>
                {name} ({ni},{nj}) 深度 {nz} · |Δ|={Math.abs(nz - z)} {ok ? "✓" : "✗"}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}
