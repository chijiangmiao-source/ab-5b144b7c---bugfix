import React from "react";
import { depthColor } from "./util.js";

// Top-down lateral map (rows x cols). Fill encodes canonical depth;
// a ring shows how many depths remain possible in some optimal surface,
// and a small glyph marks ambiguous columns.
export default function TopView({ result, selected, onPick }) {
  const { rows, cols, depth } = result;
  return (
    <div className="top-wrap">
      <div
        className="top-grid"
        style={{
          gridTemplateColumns: `22px repeat(${cols}, minmax(20px, 1fr))`,
          gridTemplateRows: `16px repeat(${rows}, minmax(22px, 1fr))`,
        }}
      >
        <div />
        {Array.from({ length: cols }, (_, j) => (
          <div key={`h${j}`} className="axis-x">{j}</div>
        ))}
        {Array.from({ length: rows }, (_, i) => (
          <React.Fragment key={`r${i}`}>
            <div className="axis-y">{i}</div>
            {Array.from({ length: cols }, (_, j) => {
              const z = result.canonical_depth[i][j];
              const opts = result.optional_depths[i][j];
              const isSel = selected[0] === i && selected[1] === j;
              const span = opts.length - 1;
              return (
                <button
                  key={`${i}:${j}`}
                  type="button"
                  className={`top-cell ${isSel ? "sel" : ""} ${opts.length > 1 ? "amb" : ""}`}
                  style={{
                    background: depthColor(depth <= 1 ? 0 : z / (depth - 1)),
                  }}
                  title={
                    `(${i}, ${j})\n规范深度 ${z}\n可选深度 ${opts.join(", ") || "（无）"}\n` +
                    `歧义跨度 ${span}`
                  }
                  onClick={() => onPick(i, j)}
                >
                  <span className="top-z">{z}</span>
                  {opts.length > 1 && (
                    <span
                      className="amb-ring"
                      style={{ opacity: 0.35 + 0.6 * Math.min(1, span / Math.max(1, depth - 1)) }}
                    />
                  )}
                </button>
              );
            })}
          </React.Fragment>
        ))}
      </div>
      <div className="legend">
        <span>浅 <i className="depth-scale" /> 深（规范深度）</span>
        <span><i className="sw amb-ring-sw" />存在多深度可选</span>
      </div>
    </div>
  );
}
