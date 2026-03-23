from pathlib import Path

import platform_context_service
from platform_context_service import PlatformContextService, ServiceConfig, TokenHashEmbedder


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def make_repo(tmp_path: Path) -> Path:
    write(
        tmp_path / "docs" / "adr" / "0042-step-ca.md",
        "# ADR 0042\n\n## Decision\nstep-ca issues SSH certificates for humans, agents, services, and hosts.\n",
    )
    write(tmp_path / "docs" / "runbooks" / "configure-step-ca.md", "# Step CA\n\n## Verify\nCheck SSH certificate issuance.\n")
    write(tmp_path / "receipts" / "live-applies" / "2026-03-22-test.json", '{"receipt_id":"r1","workflow_id":"converge-step-ca","summary":"ok","applied_on":"2026-03-22"}')
    write(tmp_path / "config" / "workflow-catalog.json", '{"workflows":{"converge-step-ca":{"description":"d"}}}')
    write(tmp_path / "config" / "command-catalog.json", '{"commands":{"converge-step-ca":{"description":"d"}}}')
    write(
        tmp_path / "config" / "service-capability-catalog.json",
        '{"services":[{"id":"grafana","name":"Grafana","description":"Monitoring UI","category":"observability","lifecycle_status":"active","vm":"monitoring-lv3","exposure":"public","public_url":"https://grafana.lv3.org","environments":{"production":{"status":"active","url":"https://grafana.lv3.org"}}},{"id":"step_ca","name":"step-ca","description":"Certificate authority","category":"security","lifecycle_status":"active","vm":"docker-runtime-lv3","exposure":"private-only","internal_url":"https://10.10.10.20:9443","environments":{"production":{"status":"active","url":"https://10.10.10.20:9443"}}}]}',
    )
    write(
        tmp_path / "config" / "slo-catalog.json",
        '{"schema_version":"1.0.0","review_note":"review later","slos":[{"id":"grafana-availability","service_id":"grafana","indicator":"availability","objective_percent":99.5,"window_days":30,"target_url":"https://grafana.lv3.org","probe_module":"http_2xx_follow_redirects","description":"Grafana stays up."}]}',
    )
    write(tmp_path / "config" / "agent-tool-registry.json", '{"tools":[]}')
    write(
        tmp_path / "config" / "dependency-graph.json",
        '{"schema_version":"1.0.0","nodes":[{"id":"step_ca","service":"step_ca","name":"step-ca","vm":"docker-runtime-lv3","tier":1}],"edges":[]}',
    )
    write(
        tmp_path / "versions" / "stack.yaml",
        "platform_version: 1.2.3\nobserved_state:\n  checked_at: 2026-03-22\n  proxmox:\n    version: 9.1.6\n  open_webui:\n    host_tailscale_proxy_url: http://100.118.189.95:8008\n  windmill:\n    host_tailscale_proxy_url: http://100.118.189.95:8005\n  netbox:\n    host_tailscale_proxy_url: http://100.118.189.95:8004\n",
    )
    write(tmp_path / "VERSION", "1.2.3\n")
    write(tmp_path / "changelog.md", "# Changelog\n")
    return tmp_path


def test_query_returns_cited_step_ca_chunk(tmp_path: Path) -> None:
    repo_root = make_repo(tmp_path)
    service = PlatformContextService(
        ServiceConfig(
            api_token="test-token",
            corpus_root=repo_root,
            collection_name="test",
            qdrant_url=None,
            qdrant_location=":memory:",
            embedding_backend="token-hash",
            embedding_model="unused",
            embedding_dimension=384,
        )
    )
    rebuild_result = service.rebuild_from_local_corpus()
    assert rebuild_result["indexed_chunks"] > 0

    result = service.query("how does step-ca issue SSH certificates", 3)
    assert result["matches"]
    assert result["matches"][0]["source_path"].startswith("docs/")
    assert "SSH certificates" in result["matches"][0]["content"]


def test_sentence_transformers_backend_falls_back_to_token_hash(tmp_path: Path, monkeypatch) -> None:
    repo_root = make_repo(tmp_path)

    class BrokenSentenceTransformersEmbedder:
        def __init__(self, model_name: str) -> None:
            raise RuntimeError(f"cannot load {model_name}")

    monkeypatch.setattr(
        platform_context_service,
        "SentenceTransformersEmbedder",
        BrokenSentenceTransformersEmbedder,
    )

    service = PlatformContextService(
        ServiceConfig(
            api_token="test-token",
            corpus_root=repo_root,
            collection_name="test",
            qdrant_url=None,
            qdrant_location=":memory:",
            embedding_backend="sentence-transformers",
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            embedding_dimension=384,
        )
    )

    assert isinstance(service.embedder, TokenHashEmbedder)
    rebuild_result = service.rebuild_from_local_corpus()
    assert rebuild_result["indexed_chunks"] > 0


def test_platform_slos_return_catalog_entries(tmp_path: Path) -> None:
    repo_root = make_repo(tmp_path)
    service = PlatformContextService(
        ServiceConfig(
            api_token="test-token",
            corpus_root=repo_root,
            collection_name="test",
            qdrant_url=None,
            qdrant_location=":memory:",
            embedding_backend="token-hash",
            embedding_model="unused",
            embedding_dimension=384,
            prometheus_url="",
            grafana_url="https://grafana.lv3.org",
        )
    )

    payload = service.slo_status()
    assert payload["slos"]
    assert payload["slos"][0]["id"] == "grafana-availability"
    assert payload["slos"][0]["metrics_available"] is False


def test_dependency_graph_methods_return_expected_payload(tmp_path: Path) -> None:
    repo_root = make_repo(tmp_path)
    service = PlatformContextService(
        ServiceConfig(
            api_token="test-token",
            corpus_root=repo_root,
            collection_name="test",
            qdrant_url=None,
            qdrant_location=":memory:",
            embedding_backend="token-hash",
            embedding_model="unused",
            embedding_dimension=384,
        )
    )

    graph = service.dependency_graph()
    impact = service.dependency_impact("step_ca")

    assert any(node["id"] == "step_ca" for node in graph["nodes"])
    assert impact["service"] == "step_ca"
    assert impact["affected"] == []
