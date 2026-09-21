import React, { useMemo } from "react";
import { columnCosts, isForbidden, costColor } from "./util.js";

// One B-scan-like slice: columns on x, depth on y (0 at top).
// Cells are cost-coloured; canonical depth carries a bright marker and the
// full optional-depth set gets an outline so the ambiguity band is visible.
export default function SliceView({ result, row, costsObj, selectedCol,
                                    forbidMode, onPick }) {
  const { cols, depth } = result;
  const forbiddenSet = useMemo(() => {
    const s = new Set();
    (costsObj?.forbidden || []).forEach(([i, j, k]) => {
      if (i === row) s.add(`${j}:${k}`);
    });
    return s;
  }, [costsObj, row]);

  const colsData = [];
  for (let j = 0; j < cols; j++) {
    const costs = costsObj ? columnCosts(costsObj, row, j) : null;
    colsData.push({
      costs,
      canon: result.canonical_depth[row][j],
      opts: new Set(result.optional_depths[row][j]),
    });
  }

  // Build in row-major depth order: rendering indexes cells[k*cols + j].
  const cells = [];
  for (let k = 0; k < depth; k++) {
    for (let j = 0; j < cols; j++) {
      const data = colsData[j];
      const key = `${j}:${k}`;
      const forb = forbiddenSet.has(key);
      const isCanon = data.canon === k;
      const isOpt = data.opts.has(k);
      const bg = data.costs
        ? (forb ? "repeating-linear-gradient(45deg,#444,#444 4px,#888 4px,#888 8px)"
                : costColor(data.costs[k]))
        : "#f2f2f2";
      cells.push(
        <button
          key={key}
          type="button"
          className={`cell ${j === selectedCol ? "col-sel" : ""} ${
            isOpt ? "opt" : ""
          } ${forb ? "forbidden" : ""}`}
          style={{ background: bg }}
          title={`列 ${j} 深度 ${k}${forb ? "（禁用）" : ""}${
            data.costs ? `\n代价 ${data.costs[k]}` : ""
          }${isCanon ? "\n规范深度" : ""}${isOpt ? "\n可出现在某最优表面" : ""}`}
          onClick={() => onPick(j, k)}
        >
          {isCanon && <span className="canon-marker" />}
        </button>
      );
    }
  }

  return (
    <div className="slice-wrap">
      <div
        className="slice-grid"
        style={{
          gridTemplateColumns: `28px repeat(${cols}, minmax(16px, 1fr))`,
          gridTemplateRows: `18px repeat(${depth}, minmax(8px, 1fr))`,
        }}
      >
        <div />
        {Array.from({ length: cols }, (_, j) => (
          <div key={`h${j}`} className={`axis-x ${j === selectedCol ? "axis-sel" : ""}`}>
            {j}
          </div>
        ))}
        {Array.from({ length: depth }, (_, k) => (
          <React.Fragment key={`rowline${k}`}>
            <div className="axis-y">{k}</div>
            {Array.from({ length: cols }, (_, j) => cells[k * cols + j])}
          </React.Fragment>
        ))}
      </div>
      <div className="legend">
        <span><i className="sw canon-sw" />规范深度</span>
        <span><i className="sw opt-sw" />可选深度（任一最优表面）</span>
        <span><i className="sw forb-sw" />禁用体素</span>
        {forbidMode && <span className="forbid-hint">点击单元格切换禁用</span>}
      </div>
    </div>
  );
}
