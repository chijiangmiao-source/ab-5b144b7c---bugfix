"""
ISAP (improved shortest augmenting path) maximum flow with the gap
heuristic, hand-written for the large, sparse grid graphs built by the
surface min-cut solver (~10^5 nodes).  Capacities are exact integers.

Residual arcs share the storage convention used elsewhere:
parallel arrays ``to/cap/nxt`` with forward/reverse arcs paired by XOR.

Only one reverse BFS from the sink is performed; afterwards distances
are maintained by relabelling.  An empty distance level triggers the
gap heuristic (every node above the gap can never reach the sink again).
The augmenting-path DFS is iterative.

After the flow, :meth:`ISAP.mincut_classification` derives the exact
min-cut-lattice (Picard-Queyranne) facts the solver needs from two
breadth-first searches plus one Kosaraju pass -- no transitive closure
is ever approximated, so the answers are exact at every graph size.
"""

from __future__ import annotations

from collections import deque


class ISAP:
    __slots__ = ("n", "head", "to", "nxt", "cap", "dist", "cnt")

    def __init__(self, n: int):
        self.n = n
        self.head = [-1] * n
        self.to: list[int] = []
        self.nxt: list[int] = []
        self.cap: list[int] = []

    def add_edge(self, u: int, v: int, capacity: int) -> None:
        self.to.append(v)
        self.cap.append(capacity)
        self.nxt.append(self.head[u])
        self.head[u] = len(self.to) - 1

        self.to.append(u)
        self.cap.append(0)
        self.nxt.append(self.head[v])
        self.head[v] = len(self.to) - 1

    def max_flow(self, s: int, t: int, limit: int | None = None) -> int:
        n = self.n
        head, to, nxt, cap = self.head, self.to, self.nxt, self.cap

        # Initial exact distances to t over residual arcs (all reverse
        # arcs start at capacity zero, so the original graph suffices).
        dist = [n] * n
        dist[t] = 0
        q = deque([t])
        while q:
            u = q.popleft()
            nd = dist[u] + 1
            e = head[u]
            while e != -1:
                v = to[e]
                # residual v -> u exists iff twin u -> v has capacity
                if dist[v] == n and cap[e ^ 1] > 0:
                    dist[v] = nd
                    q.append(v)
                e = nxt[e]

        if dist[s] == n:
            return 0

        cnt = [0] * (n + 1)
        for d in dist:
            cnt[d] += 1

        cur = list(head)
        flow = 0
        # Path of (node, arc used to leave it).
        path_v = [s]
        path_e: list[int] = []
        u = s

        while dist[s] < n:
            if u == t:
                bottle = limit - flow if limit is not None else 10**30
                for e in path_e:
                    if cap[e] < bottle:
                        bottle = cap[e]
                for e in path_e:
                    cap[e] -= bottle
                    cap[e ^ 1] += bottle
                flow += bottle
                if limit is not None and flow >= limit:
                    return flow
                # Backtrack to the first saturated arc; its source node
                # keeps scanning for another outgoing arc.
                cut = next(i for i, e in enumerate(path_e) if cap[e] == 0)
                u = path_v[cut]
                del path_v[cut + 1:]
                del path_e[cut:]
                continue

            # Find an admissible outgoing arc.
            e = cur[u]
            found = -1
            while e != -1:
                if cap[e] > 0 and dist[u] == dist[to[e]] + 1:
                    found = e
                    break
                e = nxt[e]
            cur[u] = e

            if found != -1:
                v = to[found]
                path_v.append(v)
                path_e.append(found)
                u = v
                continue

            # No admissible arc: relabel u to 1 + min neighbour distance.
            old = dist[u]
            new_d = n
            e2 = head[u]
            while e2 != -1:
                if cap[e2] > 0:
                    dv = dist[to[e2]] + 1
                    if dv < new_d:
                        new_d = dv
                e2 = nxt[e2]

            cnt[old] -= 1
            dist[u] = new_d
            cnt[new_d] += 1
            cur[u] = head[u]

            if cnt[old] == 0:
                # Gap heuristic: no node remains at level `old`, so every
                # node above it is disconnected from t in the admissible
                # subgraph. Pin their distances to n, reset their arc
                # cursors, and restart the search from the source: any path
                # that led through the current node is no longer admissible.
                for w in range(n):
                    if old < dist[w] < n:
                        cnt[dist[w]] -= 1
                        dist[w] = n
                        cnt[n] += 1
                        cur[w] = head[w]
                path_v[:] = [s]
                path_e.clear()
                u = s
                continue
            elif u != s:
                # Backtrack one hop: the predecessor must find another arc.
                path_v.pop()
                path_e.pop()
                u = path_v[-1]
            else:
                # Source relabelled below the exit condition; the path is
                # always just [s] here.
                u = s

        self.dist = dist
        return flow

    def reachable_from(self, s: int) -> list[bool]:
        """Nodes reachable from s over residual arcs (source min-cut side)."""
        seen = [False] * self.n
        seen[s] = True
        stack = [s]
        head, to, nxt, cap = self.head, self.to, self.nxt, self.cap
        while stack:
            u = stack.pop()
            e = head[u]
            while e != -1:
                v = to[e]
                if cap[e] > 0 and not seen[v]:
                    seen[v] = True
                    stack.append(v)
                e = nxt[e]
        return seen

    def residual_graph(self) -> tuple[list[list[int]], list[list[int]]]:
        g: list[list[int]] = [[] for _ in range(self.n)]
        gr: list[list[int]] = [[] for _ in range(self.n)]
        head, to, nxt, cap = self.head, self.to, self.nxt, self.cap
        for u in range(self.n):
            e = head[u]
            gu = g[u]
            while e != -1:
                if cap[e] > 0:
                    v = to[e]
                    gu.append(v)
                    gr[v].append(u)
                e = nxt[e]
        return g, gr

    def mincut_classification(self, s: int, t: int):
        """Exact min-cut-lattice classification of every node.

        Returns ``(comp, source_side, sink_reaching)``:

        * ``source_side[v]``   -- v is reachable from s over residual arcs,
          i.e. v lies on the source side of EVERY minimum s-t cut (the
          source-reachable set is itself the component-wise smallest cut);
        * ``sink_reaching[v]`` -- v can reach t over residual arcs, i.e. v
          lies on the sink side of EVERY minimum cut;
        * ``comp[v]``          -- id of v's strongly connected component in
          the residual graph (Kosaraju).  Two nodes can be separated by a
          minimum cut iff they sit in different components AND neither
          side is forced by the two reachability sets above.
        """
        g, gr = self.residual_graph()
        n = self.n

        source_side = self.reachable_from(s)

        # Nodes that can reach t: BFS from t over reversed residual arcs.
        sink_reaching = [False] * n
        sink_reaching[t] = True
        stack = [t]
        while stack:
            u = stack.pop()
            for v in gr[u]:
                if not sink_reaching[v]:
                    sink_reaching[v] = True
                    stack.append(v)

        # Kosaraju: first pass orders nodes by finishing time on g, second
        # pass expands components on gr.
        visited = bytearray(n)
        order: list[int] = []
        for start in range(n):
            if visited[start]:
                continue
            visited[start] = 1
            stack: list[tuple[int, int]] = [(start, 0)]
            while stack:
                u, ei = stack[-1]
                if ei < len(g[u]):
                    v = g[u][ei]
                    stack[-1] = (u, ei + 1)
                    if not visited[v]:
                        visited[v] = 1
                        stack.append((v, 0))
                else:
                    order.append(u)
                    stack.pop()

        comp = [-1] * n
        cid = 0
        for start in reversed(order):
            if comp[start] != -1:
                continue
            comp[start] = cid
            stack = [start]
            while stack:
                u = stack.pop()
                for v in gr[u]:
                    if comp[v] == -1:
                        comp[v] = cid
                        stack.append(v)
            cid += 1

        return comp, source_side, sink_reaching
