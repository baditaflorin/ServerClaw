from pathlib import Path

import httpx

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
        tmp_path / "config" / "error-codes.yaml",
        """schema_version: 1.0.0
error_codes:
  AUTH_TOKEN_MISSING:
    http_status: 401
    severity: warn
    category: authentication
    retry_advice: none
    description: Bearer token is required for this endpoint.
    context_fields: [header]
  AUTH_TOKEN_INVALID:
    http_status: 401
    severity: warn
    category: authentication
    retry_advice: none
    description: Bearer token is invalid.
    context_fields: [header]
  INPUT_SCHEMA_INVALID:
    http_status: 422
    severity: warn
    category: input
    retry_advice: none
    description: Request payload or parameters failed validation.
    context_fields: [field_path, error_type, validation_message]
  INPUT_UNKNOWN_WORKFLOW:
    http_status: 404
    severity: info
    category: input
    retry_advice: none
    description: Requested workflow is not defined.
    context_fields: [workflow_id]
  INPUT_UNKNOWN_COMMAND:
    http_status: 404
    severity: info
    category: input
    retry_advice: none
    description: Requested command is not defined.
    context_fields: [command_id]
  INPUT_UNKNOWN_SERVICE:
    http_status: 404
    severity: info
    category: input
    retry_advice: none
    description: Requested platform service is not defined.
    context_fields: [service_id]
  INTERNAL_UNEXPECTED_ERROR:
    http_status: 500
    severity: error
    category: internal
    retry_advice: manual
    description: Unexpected internal error.
    context_fields: [detail]
""",
    )
    write(
        tmp_path / "config" / "slo-catalog.json",
        '{"schema_version":"1.0.0","review_note":"review later","slos":[{"id":"grafana-availability","service_id":"grafana","indicator":"availability","objective_percent":99.5,"window_days":30,"target_url":"https://grafana.lv3.org","probe_module":"http_2xx_follow_redirects","description":"Grafana stays up."}]}',
    )
    write(tmp_path / "config" / "agent-tool-registry.json", '{"tools":[]}')
    write(
        tmp_path / "config" / "dependency-graph.json",
        '{"schema_version":"1.0.0","nodes":[{"id":"grafana","service":"grafana","name":"Grafana","vm":"monitoring-lv3","tier":1},{"id":"step_ca","service":"step_ca","name":"step-ca","vm":"docker-runtime-lv3","tier":1}],"edges":[]}',
    )
    write(
        tmp_path / "versions" / "stack.yaml",
        "platform_version: 1.2.3\nobserved_state:\n  checked_at: 2026-03-22\n  proxmox:\n    version: 9.1.6\n  monitoring:\n    prometheus_internal_url: http://100.118.189.95:9090\n  open_webui:\n    host_tailscale_proxy_url: http://100.118.189.95:8008\n  windmill:\n    host_tailscale_proxy_url: http://100.118.189.95:8005\n  netbox:\n    host_tailscale_proxy_url: http://100.118.189.95:8004\n",
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
            error_registry_path=repo_root / "config" / "error-codes.yaml",
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
    assert any(match["source_path"].startswith("docs/") for match in result["matches"])
    assert any("SSH certificates" in match["content"] for match in result["matches"])


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
            error_registry_path=repo_root / "config" / "error-codes.yaml",
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
            error_registry_path=repo_root / "config" / "error-codes.yaml",
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
            error_registry_path=repo_root / "config" / "error-codes.yaml",
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


def test_platform_context_http_sets_trace_header(tmp_path: Path) -> None:
    repo_root = make_repo(tmp_path)
    service = PlatformContextService(
        ServiceConfig(
            api_token="test-token",
            corpus_root=repo_root,
            error_registry_path=repo_root / "config" / "error-codes.yaml",
            collection_name="test",
            qdrant_url=None,
            qdrant_location=":memory:",
            embedding_backend="token-hash",
            embedding_model="unused",
            embedding_dimension=384,
        )
    )

    previous_service = platform_context_service.service
    platform_context_service.service = service
    async def run() -> None:
        try:
            transport = httpx.ASGITransport(app=platform_context_service.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://platform-context.test") as client:
                response = await client.get(
                    "/v1/platform-summary",
                    headers={"Authorization": "Bearer test-token", "X-Trace-Id": "trace-context-123"},
                )
                assert response.status_code == 200
                assert response.headers["X-Trace-Id"] == "trace-context-123"
                assert response.json()["repo_version"] == "1.2.3"
        finally:
            platform_context_service.service = previous_service

    import asyncio

    asyncio.run(run())


def test_build_config_uses_corpus_root_for_default_observability_paths(tmp_path: Path, monkeypatch) -> None:
    repo_root = make_repo(tmp_path)
    monkeypatch.setenv("PLATFORM_CONTEXT_API_TOKEN", "test-token")
    monkeypatch.setenv("PLATFORM_CONTEXT_CORPUS_ROOT", str(repo_root))
    monkeypatch.delenv("PLATFORM_CONTEXT_PROMETHEUS_URL", raising=False)
    monkeypatch.delenv("PLATFORM_CONTEXT_GRAFANA_URL", raising=False)

    config = platform_context_service.build_config()

    assert config.error_registry_path == repo_root / "config" / "error-codes.yaml"
    assert config.prometheus_url == "http://100.118.189.95:9090"
    assert config.grafana_url == "https://grafana.lv3.org"


def test_platform_context_app_returns_canonical_errors(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    repo_root = make_repo(tmp_path)
    platform_context_service.service = PlatformContextService(
        ServiceConfig(
            api_token="test-token",
            corpus_root=repo_root,
            error_registry_path=repo_root / "config" / "error-codes.yaml",
            collection_name="test",
            qdrant_url=None,
            qdrant_location=":memory:",
            embedding_backend="token-hash",
            embedding_model="unused",
            embedding_dimension=384,
        )
    )
    client = TestClient(platform_context_service.app)
    try:
        unauthorized = client.get("/v1/platform-summary")
        assert unauthorized.status_code == 401
        assert unauthorized.json()["error"]["code"] == "AUTH_TOKEN_MISSING"

        missing_workflow = client.get(
            "/v1/workflows/missing",
            headers={"Authorization": "Bearer test-token"},
        )
        assert missing_workflow.status_code == 404
        assert missing_workflow.json()["error"]["code"] == "INPUT_UNKNOWN_WORKFLOW"

        invalid_query = client.post(
            "/v1/context/query",
            headers={"Authorization": "Bearer test-token"},
            json={"question": "hi", "top_k": 3},
        )
        assert invalid_query.status_code == 422
        assert invalid_query.json()["error"]["code"] == "INPUT_SCHEMA_INVALID"
    finally:
        platform_context_service.service = None
