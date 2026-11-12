from __future__ import annotations

"""
graph.py – in-memory network graph for FINN relationship intelligence.

Nodes: Investor (anchor), Contact (1st/2nd degree), Organisation, Institution, Executive.
Edges: Directed, typed (former_colleague, industry_introduction, professional_association,
       executive_match, employment, education).

BFS traversal is bounded at depth 2; career overlap is NOT treated as a relationship.
"""

import enum
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Iterator
from uuid import UUID


class NodeKind(str, enum.Enum):
    INVESTOR = "investor"
    CONTACT = "contact"
    ORGANISATION = "organisation"
    INSTITUTION = "institution"
    EXECUTIVE = "executive"


class EdgeKind(str, enum.Enum):
    DIRECT_RELATIONSHIP = "direct_relationship"
    SECOND_DEGREE = "second_degree"
    EMPLOYMENT = "employment"
    EDUCATION = "education"
    EXECUTIVE_MATCH = "executive_match"


@dataclass
class GraphNode:
    node_id: UUID
    kind: NodeKind
    label: str
    # Extra attributes stored as a dict for flexibility
    attrs: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    source_id: UUID
    target_id: UUID
    kind: EdgeKind
    label: str
    weight: float = 1.0  # higher = stronger
    attrs: dict = field(default_factory=dict)


class NetworkGraph:
    """
    Sparse directed graph of FINN network entities.

    Only explicitly recorded edges are stored. Career overlap
    does NOT create edges; it is stored as node attributes only.
    """

    def __init__(self) -> None:
        self._nodes: dict[UUID, GraphNode] = {}
        self._out_edges: dict[UUID, list[GraphEdge]] = defaultdict(list)
        self._in_edges: dict[UUID, list[GraphEdge]] = defaultdict(list)

    # ------------------------------------------------------------------ #
    #  Node management                                                      #
    # ------------------------------------------------------------------ #

    def add_node(self, node: GraphNode) -> None:
        self._nodes[node.node_id] = node

    def get_node(self, node_id: UUID) -> GraphNode | None:
        return self._nodes.get(node_id)

    def nodes(self, kind: NodeKind | None = None) -> Iterator[GraphNode]:
        for node in self._nodes.values():
            if kind is None or node.kind == kind:
                yield node

    # ------------------------------------------------------------------ #
    #  Edge management                                                      #
    # ------------------------------------------------------------------ #

    def add_edge(self, edge: GraphEdge) -> None:
        self._out_edges[edge.source_id].append(edge)
        self._in_edges[edge.target_id].append(edge)

    def out_edges(self, node_id: UUID, kind: EdgeKind | None = None) -> list[GraphEdge]:
        edges = self._out_edges.get(node_id, [])
        if kind is None:
            return list(edges)
        return [e for e in edges if e.kind == kind]

    def in_edges(self, node_id: UUID, kind: EdgeKind | None = None) -> list[GraphEdge]:
        edges = self._in_edges.get(node_id, [])
        if kind is None:
            return list(edges)
        return [e for e in edges if e.kind == kind]

    # ------------------------------------------------------------------ #
    #  Traversal                                                            #
    # ------------------------------------------------------------------ #

    def bfs(
        self,
        start_id: UUID,
        *,
        max_depth: int = 2,
        edge_kinds: set[EdgeKind] | None = None,
    ) -> dict[UUID, int]:
        """
        BFS from start_id up to max_depth hops.
        Returns {node_id: depth} for all reachable nodes.
        Career overlap (employment/education edges) is excluded from
        traversal unless explicitly included via edge_kinds.
        """
        if edge_kinds is None:
            # By default traverse only explicit relationship edges
            edge_kinds = {EdgeKind.DIRECT_RELATIONSHIP, EdgeKind.SECOND_DEGREE}
        visited: dict[UUID, int] = {start_id: 0}
        queue: deque[tuple[UUID, int]] = deque([(start_id, 0)])
        while queue:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for edge in self._out_edges.get(current_id, []):
                if edge.kind not in edge_kinds:
                    continue
                if edge.target_id not in visited:
                    visited[edge.target_id] = depth + 1
                    queue.append((edge.target_id, depth + 1))
        return visited

    def shortest_path(
        self,
        start_id: UUID,
        target_id: UUID,
        *,
        max_depth: int = 2,
        edge_kinds: set[EdgeKind] | None = None,
    ) -> list[GraphEdge] | None:
        """
        Returns the list of edges forming the shortest path from start to target,
        or None if no path exists within max_depth.
        Career-overlap edges are excluded unless explicitly included.
        """
        if edge_kinds is None:
            edge_kinds = {EdgeKind.DIRECT_RELATIONSHIP, EdgeKind.SECOND_DEGREE}
        if start_id == target_id:
            return []
        queue: deque[tuple[UUID, list[GraphEdge]]] = deque([(start_id, [])])
        visited: set[UUID] = {start_id}
        while queue:
            current_id, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            for edge in self._out_edges.get(current_id, []):
                if edge.kind not in edge_kinds:
                    continue
                if edge.target_id in visited:
                    continue
                new_path = [*path, edge]
                if edge.target_id == target_id:
                    return new_path
                visited.add(edge.target_id)
                queue.append((edge.target_id, new_path))
        return None

    # ------------------------------------------------------------------ #
    #  Convenience queries                                                  #
    # ------------------------------------------------------------------ #

    def neighbours(
        self,
        node_id: UUID,
        kind: EdgeKind | None = None,
    ) -> list[GraphNode]:
        """Return neighbour nodes reachable via outgoing edges."""
        return [
            self._nodes[e.target_id]
            for e in self._out_edges.get(node_id, [])
            if (kind is None or e.kind == kind) and e.target_id in self._nodes
        ]

    def contacts_at_depth(self, start_id: UUID, depth: int) -> list[GraphNode]:
        """Return contact nodes at exactly the specified depth."""
        reachable = self.bfs(start_id, max_depth=depth)
        return [
            self._nodes[nid]
            for nid, d in reachable.items()
            if d == depth and nid in self._nodes and self._nodes[nid].kind == NodeKind.CONTACT
        ]

    def __len__(self) -> int:
        return len(self._nodes)

    def __repr__(self) -> str:
        return f"NetworkGraph(nodes={len(self._nodes)}, edges={sum(len(v) for v in self._out_edges.values())})"
