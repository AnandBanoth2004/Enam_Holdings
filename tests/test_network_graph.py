"""
Tests for the FINN network graph engine: node/edge management,
BFS traversal bounded at depth 2, and path finding.

Career overlap must NOT create implicit relationship edges.
"""
from __future__ import annotations

from uuid import uuid4

from finn_api.network.graph import (
    EdgeKind,
    GraphEdge,
    GraphNode,
    NetworkGraph,
    NodeKind,
)


def _make_graph_with_contacts():
    """
    Create a small synthetic graph:
      investor -> contact_a (direct, strong)
      contact_a -> contact_b (second-degree, moderate)
      contact_b -> contact_c (second-degree, light)  # 3 hops from investor
      org_x -> contact_a (employment, not a relationship edge)
    """
    investor_id = uuid4()
    contact_a_id = uuid4()
    contact_b_id = uuid4()
    contact_c_id = uuid4()
    org_x_id = uuid4()

    graph = NetworkGraph()

    graph.add_node(GraphNode(investor_id, NodeKind.INVESTOR, "FINN Investor"))
    graph.add_node(GraphNode(contact_a_id, NodeKind.CONTACT, "Contact Alpha"))
    graph.add_node(GraphNode(contact_b_id, NodeKind.CONTACT, "Contact Beta"))
    graph.add_node(GraphNode(contact_c_id, NodeKind.CONTACT, "Contact Gamma"))
    graph.add_node(GraphNode(org_x_id, NodeKind.ORGANISATION, "Org X"))

    # Explicit relationship edges
    graph.add_edge(GraphEdge(investor_id, contact_a_id, EdgeKind.DIRECT_RELATIONSHIP, "former_colleague", weight=1.0))
    graph.add_edge(GraphEdge(contact_a_id, contact_b_id, EdgeKind.DIRECT_RELATIONSHIP, "industry_introduction", weight=0.8))
    graph.add_edge(GraphEdge(contact_b_id, contact_c_id, EdgeKind.DIRECT_RELATIONSHIP, "professional_association", weight=0.5))

    # Employment edge (should NOT be traversed in relationship BFS by default)
    graph.add_edge(GraphEdge(org_x_id, contact_a_id, EdgeKind.EMPLOYMENT, "employed_at", weight=0.0))

    return graph, investor_id, contact_a_id, contact_b_id, contact_c_id, org_x_id


def test_graph_node_and_edge_counts():
    graph, investor_id, *_ = _make_graph_with_contacts()
    assert len(graph) == 5  # 1 investor + 3 contacts + 1 org
    assert repr(graph).startswith("NetworkGraph(")


def test_bfs_depth_1_returns_direct_contacts_only():
    graph, investor_id, contact_a_id, contact_b_id, contact_c_id, org_x_id = _make_graph_with_contacts()
    reachable = graph.bfs(investor_id, max_depth=1)
    assert investor_id in reachable and reachable[investor_id] == 0
    assert contact_a_id in reachable and reachable[contact_a_id] == 1
    assert contact_b_id not in reachable
    assert contact_c_id not in reachable


def test_bfs_depth_2_includes_second_degree():
    graph, investor_id, contact_a_id, contact_b_id, contact_c_id, org_x_id = _make_graph_with_contacts()
    reachable = graph.bfs(investor_id, max_depth=2)
    assert reachable[contact_a_id] == 1
    assert reachable[contact_b_id] == 2
    # contact_c is 3 hops away, must NOT appear
    assert contact_c_id not in reachable


def test_bfs_excludes_employment_edges_by_default():
    """Career overlap (employment edges) must not create implicit relationship paths."""
    graph, investor_id, contact_a_id, contact_b_id, contact_c_id, org_x_id = _make_graph_with_contacts()
    reachable = graph.bfs(investor_id, max_depth=2)
    # org_x is only connected via employment, must not appear in relationship BFS
    assert org_x_id not in reachable


def test_shortest_path_first_degree():
    graph, investor_id, contact_a_id, contact_b_id, contact_c_id, org_x_id = _make_graph_with_contacts()
    path = graph.shortest_path(investor_id, contact_a_id)
    assert path is not None
    assert len(path) == 1
    assert path[0].source_id == investor_id
    assert path[0].target_id == contact_a_id


def test_shortest_path_second_degree():
    graph, investor_id, contact_a_id, contact_b_id, contact_c_id, org_x_id = _make_graph_with_contacts()
    path = graph.shortest_path(investor_id, contact_b_id)
    assert path is not None
    assert len(path) == 2
    assert path[0].target_id == contact_a_id
    assert path[1].target_id == contact_b_id


def test_shortest_path_exceeds_max_depth_returns_none():
    """3-hop path must return None when max_depth=2."""
    graph, investor_id, contact_a_id, contact_b_id, contact_c_id, org_x_id = _make_graph_with_contacts()
    path = graph.shortest_path(investor_id, contact_c_id, max_depth=2)
    assert path is None


def test_contacts_at_depth():
    graph, investor_id, contact_a_id, contact_b_id, contact_c_id, org_x_id = _make_graph_with_contacts()
    first_degree = graph.contacts_at_depth(investor_id, 1)
    second_degree = graph.contacts_at_depth(investor_id, 2)
    assert len(first_degree) == 1
    assert first_degree[0].node_id == contact_a_id
    assert len(second_degree) == 1
    assert second_degree[0].node_id == contact_b_id


def test_no_self_loop_traversal():
    """Ensure start node is not returned at depth > 0."""
    graph, investor_id, *_ = _make_graph_with_contacts()
    reachable = graph.bfs(investor_id, max_depth=2)
    assert reachable[investor_id] == 0  # only at depth 0


def test_employment_edge_included_when_explicitly_requested():
    """When edge_kinds includes EMPLOYMENT, those edges are traversable."""
    graph, investor_id, contact_a_id, contact_b_id, contact_c_id, org_x_id = _make_graph_with_contacts()
    reachable = graph.bfs(
        org_x_id,
        max_depth=1,
        edge_kinds={EdgeKind.EMPLOYMENT},
    )
    assert contact_a_id in reachable


def test_executive_node_in_graph():
    """Executives can be represented as nodes and connected via executive_match edges."""
    graph = NetworkGraph()
    exec_id = uuid4()
    contact_id = uuid4()
    graph.add_node(GraphNode(exec_id, NodeKind.EXECUTIVE, "Mira Deshpande [SYNTHETIC DEMO]"))
    graph.add_node(GraphNode(contact_id, NodeKind.CONTACT, "Network Contact Alpha"))
    graph.add_edge(GraphEdge(exec_id, contact_id, EdgeKind.EXECUTIVE_MATCH, "proposed_name_match", weight=0.97))
    assert graph.get_node(exec_id) is not None
    assert len(graph.out_edges(exec_id, EdgeKind.EXECUTIVE_MATCH)) == 1
