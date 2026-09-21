# OCT 规范表面审计台（Exact Surface Audit Console）

从 OCT 代价体（cost volume）中为每个横向位置选出**同一层界面**的全栈审计工具：

- 前端 React 页面可编辑 / 粘贴代价体与参数；
- 经真实 **FastAPI** 接口，由后端用**精确整数**算法求最小总代价表面；
- 以**切片图**与**俯视图**显示规范表面和每列的歧义（可选深度）范围；
- 点击任一列可对照规范深度、该列全部可选深度与逐深度代价；
- 不调用任何通用优化求解器（无 LP/MIP/网络流第三方库），结果可重算、可审计。

## 问题定义与保证

横向 `rows × cols`（各 2–40），深度 `depth`（2–64），代价为 `0..1_000_000` 的整数。

- 每个横向列恰好选一个深度 `z[r,c] ∈ [0, depth)`；
- 四邻深度差 `|z[r,c] − z[r',c']| ≤ S`（S ≥ 0 整数）；
- `forbidden` 中列出的 `[row, col, depth]` 体素不得被选；
- 目标：最小化总代价 `Σ cost[r,c,z[r,c]]`（精确整数，无浮点误差）。

输出保证：

1. **全局最优**：总代价精确最小；
2. **规范解**：多个最优表面时，取**行主序深度向量的字典序最小**者；
3. **完整歧义集合**：给出每列在**任一最优表面**中可出现的全部深度；
4. **可行性**：无可行表面时明确返回 `infeasible`；输入非法时返回定位到字段/索引的错误，前端保留草稿不清空；
5. **唯一性**：明确标注「唯一最优表面」或「存在多个最优表面」。

## 算法（精确整数，无通用求解器）

见 `backend/app/solver.py` 顶部完整推导。要点：

- 有序标签 + 凸成对势（硬斜率限制）被**精确归约**为整数 s-t 最小割
  （单调阈值链构造：链内无穷边、一元代价差分边、禁用体素边、四邻跨列边）；
- 最大流由 `backend/app/isap.py` 中**手写的整数 ISAP**（最短增广路 + gap 启发式）计算；
- 流后对残量网络做两次 BFS（源点正向、汇点反向）与 SCC（Kosaraju）精确分类
  （最小割格 / Picard–Queyranne 结构，不做任何传递闭包近似）：
  - 源点可达集即最小割，且是分量最小割 ⇒ 对应行主序字典序最小规范表面；
  - 深度 *a* 在某最优表面中可选，当且仅当阈值节点 v(t,a) 不到达汇点、
    v(t,a+1) 不从源点可达、且二者分属不同残量 SCC——链上无穷边
    v(t,a+1)→v(t,a) 恒为残量边，故"存在 v(t,a)~>v(t,a+1) 残量路径"
    当且仅当二者同属一个 SCC（最小割格分离判据的精确线性判定）。
- 两条数学特例同样精确（与一般构造结果一致，仅在大规模时显著省时）：
  `S=0` 时连通网格强制全局统一深度，枚举 D 个常量解；
  `S≥D−1` 时约束消失，逐列独立取最小。

正确性验证：`backend/tests/test_bruteforce.py` 对 **400 个随机实例**穷举全部可行表面，
逐一核对最优代价、字典序规范解、逐列可选深度集合，全部一致。

## 目录结构

```
backend/    FastAPI 服务 + 精确求解器（solver.py / isap.py）+ 测试
frontend/   React + Vite 单页应用 + nginx 镜像配置
verify/     一次性端到端验收脚本（HTTP 实测 + 独立暴力核验）
docker-compose.yml
```

## 用 Docker Compose 运行

宿主机 Web/API 端口可用环境变量配置（默认 Web `8080`、API `8000`）：

```bash
cp .env.example .env        # 按需修改 WEB_PORT / API_PORT
docker compose up --build
```

- Web 界面： http://localhost:8080
- API 文档： http://localhost:8000/docs （健康检查 `GET /health`）

两个容器都声明了 `HEALTHCHECK`：API 检查 FastAPI `/health`；Web 检查经 nginx
代理到 API 的 `/health`，即全链路就绪后才为 healthy。

### 一次性端到端验收（verify 服务）

`verify` 是一次性服务，经 HTTP 实测整个技术栈（nginx → FastAPI），独立暴力核验
最优代价/规范解/可选深度，覆盖多解、不可行、非法输入定位、扁平代价数组与
40×40×64 最大规模请求；**执行后自行退出，并以退出码报告结果**：

```bash
docker compose run --rm verify
# 全部通过：退出码 0；任一失败：退出码非 0
```

（`verify` 位于 `verify` profile，普通 `docker compose up` 不会自动运行它。）

## 请求 / 响应

`POST /api/solve`，请求体示例：

```json
{
  "rows": 2, "cols": 2, "depth": 3, "s": 1,
  "costs": [
    [[0, 5, 9], [7, 1, 8]],
    [[3, 0, 2], [4, 4, 0]]
  ],
  "forbidden": []
}
```

`costs` 也接受行主序一维整数数组（长度 `rows*cols*depth`）。成功响应：

```json
{
  "status": "feasible",
  "optimal_cost": 1,
  "canonical_depth": [[0, 1], [1, 2]],
  "canonical_cost": [[0, 1], [0, 0]],
  "optional_depths": [[[[0]], [[1]]], [[[1]], [[2]]]],
  "unique": true,
  "ambiguous_columns": 0,
  "elapsed_ms": 9.3
}
```

无可行表面：`"status": "infeasible"`，`optimal_cost` 与表面字段为 `null`。
输入非法：HTTP 422，`errors` 为定位到具体字段/索引（如 `forbidden[3]`、
`costs[1][2]`）的中文原因列表；前端不覆盖当前草稿。

## 本地开发（不用 Docker）

```bash
# 后端
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端（:5173，/api 与 /health 代理到 8000）
cd frontend
npm install && npm run dev
```

后端测试：

```bash
cd backend
python tests/test_bruteforce.py     # 400 例穷举对照（退出码报告）
pip install pytest httpx && python -m pytest tests/
```

## 前端操作

1. 用参数框或直接编辑 JSON 草稿（低信噪 / 多解 / 不可行三个内置示例）；
2. 「提交求解」调用真实接口；非法或不可行时原因就地展示、**草稿保留**；
3. 切片图：横轴列、纵轴深度；白点＝规范深度，紫框＝该列全部可选深度，斜纹＝禁用体素；
   勾选「禁用编辑模式」后点单元格可增删禁用体素；
4. 俯视图：每格颜色＝规范深度，虚框＝存在多深度可选，数字为规范深度；
5. 点任意列（切片或俯视图）：下方审计卡给出规范深度及其代价、全局最优总代价、
   完整可选深度集合、逐深度代价柱与表格、四邻 `|Δ|≤S` 核对，并标明该列唯一或多解。
