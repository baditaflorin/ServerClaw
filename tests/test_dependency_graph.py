from __future__ import annotations

import json

import dependency_graph


def test_dependency_graph_validates_against_service_catalog() -> None:
    graph = dependency_graph.load_dependency_graph(validate_schema=True)
    assert len(graph.nodes) == 23
    assert graph.nodes["ops_portal"].tier == 4


def test_compute_impact_for_postgres_includes_direct_and_transitive_failures() -> None:
    graph = dependency_graph.load_dependency_graph(validate_schema=False)
    impact = dependency_graph.compute_impact("postgres", graph)

    assert set(impact.direct_hard) == {"keycloak", "mattermost", "netbox", "windmill"}
    assert set(impact.transitive_hard) == {"api_gateway", "ops_portal"}


def test_deployment_order_sorts_dependencies_before_dependents() -> None:
    graph = dependency_graph.load_dependency_graph(validate_schema=False)
    ordered = dependency_graph.deployment_order(
        ["ops_portal", "windmill", "postgres", "keycloak"],
        graph,
    )
    assert ordered == ["postgres", "keycloak", "windmill", "ops_portal"]


def test_render_dependency_markdown_contains_mermaid_and_tiers() -> None:
    graph = dependency_graph.load_dependency_graph(validate_schema=False)
    markdown = dependency_graph.render_dependency_markdown(graph)

    assert "```mermaid" in markdown
    assert "| `4` | Ops Portal |" in markdown


def test_graph_to_dict_is_json_serializable() -> None:
    graph = dependency_graph.load_dependency_graph(validate_schema=False)
    payload = dependency_graph.graph_to_dict(graph)
    json.dumps(payload)
    assert payload["edges"]
