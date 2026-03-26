from pathlib import Path

from canonical_errors import ErrorRegistry


def test_error_registry_filters_context_to_declared_fields(tmp_path: Path) -> None:
    registry_path = tmp_path / "error-codes.yaml"
    registry_path.write_text(
        """schema_version: 1.0.0
error_codes:
  INPUT_UNKNOWN_WORKFLOW:
    http_status: 404
    severity: info
    category: input
    retry_advice: none
    description: Requested workflow is unknown.
    context_fields: [workflow_id]
""",
        encoding="utf-8",
    )

    registry = ErrorRegistry.load(registry_path)
    error = registry.create(
        "INPUT_UNKNOWN_WORKFLOW",
        trace_id="trace-123",
        message="Unknown workflow: deploy-missing",
        context={"workflow_id": "deploy-missing", "ignored": "value"},
    )

    assert error.http_status == 404
    assert error.to_response()["error"]["context"] == {"workflow_id": "deploy-missing"}
    assert error.to_response()["error"]["trace_id"] == "trace-123"
