from __future__ import annotations

from log_validator import summarize, validate_line


def test_validator_accepts_valid_structured_log_line() -> None:
    result = validate_line(
        '{"ts":"2026-03-25T12:00:00.000Z","level":"INFO","service_id":"api_gateway","component":"http","trace_id":"abc123","msg":"ok","vm":"docker-runtime"}'
    )
    assert result.valid is True


def test_validator_accepts_nested_docker_log_payload() -> None:
    result = validate_line(
        '{"log":"{\\"ts\\":\\"2026-03-25T12:00:00.000Z\\",\\"level\\":\\"WARN\\",\\"service_id\\":\\"platform_context_api\\",\\"component\\":\\"http\\",\\"trace_id\\":\\"abc123\\",\\"msg\\":\\"slow query\\",\\"vm\\":\\"docker-runtime\\"}\\n","stream":"stdout","time":"2026-03-25T12:00:00.000000000Z"}'
    )
    assert result.valid is True


def test_validator_rejects_missing_required_field() -> None:
    result = validate_line(
        '{"ts":"2026-03-25T12:00:00.000Z","level":"INFO","service_id":"api_gateway","component":"http","msg":"missing trace","vm":"docker-runtime"}'
    )
    assert result.valid is False
    assert result.reason == "missing_fields:trace_id"


def test_validator_summary_groups_service_violations() -> None:
    summary = summarize(
        [
            validate_line("not-json"),
            validate_line(
                '{"ts":"2026-03-25T12:00:00.000Z","level":"INFO","service_id":"api_gateway","component":"http","msg":"missing trace","vm":"docker-runtime"}'
            ),
        ]
    )
    assert summary["valid"] is False
    assert summary["violation_count"] == 2
    assert summary["violations_by_service"]["api_gateway"] == 1
