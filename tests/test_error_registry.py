"""Tests for scripts/error_registry.py (ADR 0166).

Covers:
- Loading and validating the canonical config/error-codes.yaml
- validate_registry() schema enforcement
- load_registry() error paths
- lookup() / list_codes() / codes_by_category() convenience helpers
- All required error code categories are present in the canonical registry
- ErrorCodeDefinition fields are correctly populated
- CanonicalError.to_response() envelope shape
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from error_registry import (
    ErrorRegistryError,
    UnknownErrorCode,
    codes_by_category,
    list_codes,
    load_registry,
    lookup,
    validate_registry,
)
from canonical_errors import CanonicalError, ErrorRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_REGISTRY_PATH = REPO_ROOT / "config" / "error-codes.yaml"


def make_registry(tmp_path: Path, yaml_body: str) -> Path:
    """Write a registry file and return its path."""
    p = tmp_path / "error-codes.yaml"
    p.write_text(textwrap.dedent(yaml_body), encoding="utf-8")
    return p


def minimal_yaml(extra_codes: str = "") -> str:
    """Return a valid minimal registry YAML string with optional extra codes appended.

    *extra_codes* should contain entries at the same indentation level as the
    AUTH_TOKEN_MISSING block (i.e. two leading spaces under error_codes).
    The string is dedented and then re-indented under ``error_codes:``.
    """
    base = textwrap.dedent("""\
        schema_version: 1.0.0
        error_codes:
          AUTH_TOKEN_MISSING:
            http_status: 401
            severity: warn
            category: authentication
            retry_advice: none
            description: Bearer token is required.
            context_fields: [header]
    """)
    if extra_codes:
        # Dedent so we can re-indent uniformly under error_codes (2 spaces)
        stripped = textwrap.dedent(extra_codes)
        # Re-indent each non-blank line by 2 spaces so they sit under error_codes
        indented = "\n".join(("  " + line if line.strip() else line) for line in stripped.splitlines())
        return base + indented.strip("\n") + "\n"
    return base


# ---------------------------------------------------------------------------
# Canonical registry file
# ---------------------------------------------------------------------------


class TestCanonicalRegistryFile:
    """Tests that verify the actual config/error-codes.yaml in the repo."""

    def test_canonical_registry_exists(self) -> None:
        assert CANONICAL_REGISTRY_PATH.exists(), f"config/error-codes.yaml not found at {CANONICAL_REGISTRY_PATH}"

    def test_canonical_registry_is_valid_yaml(self) -> None:
        data = yaml.safe_load(CANONICAL_REGISTRY_PATH.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_canonical_registry_passes_validate_registry(self) -> None:
        data = yaml.safe_load(CANONICAL_REGISTRY_PATH.read_text(encoding="utf-8"))
        result = validate_registry(data)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_canonical_registry_loads_without_error(self) -> None:
        registry = load_registry(CANONICAL_REGISTRY_PATH)
        assert registry is not None

    def test_canonical_registry_has_auth_codes(self) -> None:
        codes = list_codes(registry_path=CANONICAL_REGISTRY_PATH)
        auth_codes = [c for c in codes if c.startswith("AUTH_")]
        assert len(auth_codes) >= 4, f"Expected >= 4 AUTH_* codes, got: {auth_codes}"
        assert "AUTH_TOKEN_MISSING" in auth_codes
        assert "AUTH_TOKEN_INVALID" in auth_codes
        assert "AUTH_TOKEN_EXPIRED" in auth_codes
        assert "AUTH_INSUFFICIENT_ROLE" in auth_codes

    def test_canonical_registry_has_authz_codes(self) -> None:
        codes = list_codes(registry_path=CANONICAL_REGISTRY_PATH)
        authz_codes = [c for c in codes if c.startswith("AUTHZ_")]
        assert len(authz_codes) >= 2, f"Expected >= 2 AUTHZ_* codes, got: {authz_codes}"

    def test_canonical_registry_has_health_codes(self) -> None:
        codes = list_codes(registry_path=CANONICAL_REGISTRY_PATH)
        health_codes = [c for c in codes if c.startswith("HEALTH_")]
        assert len(health_codes) >= 2, f"Expected >= 2 HEALTH_* codes, got: {health_codes}"

    def test_canonical_registry_has_probe_codes(self) -> None:
        codes = list_codes(registry_path=CANONICAL_REGISTRY_PATH)
        probe_codes = [c for c in codes if c.startswith("PROBE_")]
        assert len(probe_codes) >= 2, f"Expected >= 2 PROBE_* codes, got: {probe_codes}"

    def test_canonical_registry_has_deploy_codes(self) -> None:
        codes = list_codes(registry_path=CANONICAL_REGISTRY_PATH)
        deploy_codes = [c for c in codes if c.startswith("DEPLOY_")]
        assert len(deploy_codes) >= 2, f"Expected >= 2 DEPLOY_* codes, got: {deploy_codes}"

    def test_canonical_registry_has_converge_codes(self) -> None:
        codes = list_codes(registry_path=CANONICAL_REGISTRY_PATH)
        converge_codes = [c for c in codes if c.startswith("CONVERGE_")]
        assert len(converge_codes) >= 2, f"Expected >= 2 CONVERGE_* codes, got: {converge_codes}"

    def test_canonical_registry_has_config_codes(self) -> None:
        codes = list_codes(registry_path=CANONICAL_REGISTRY_PATH)
        config_codes = [c for c in codes if c.startswith("CONFIG_")]
        assert len(config_codes) >= 2, f"Expected >= 2 CONFIG_* codes, got: {config_codes}"

    def test_canonical_registry_has_schema_codes(self) -> None:
        codes = list_codes(registry_path=CANONICAL_REGISTRY_PATH)
        schema_codes = [c for c in codes if c.startswith("SCHEMA_")]
        assert len(schema_codes) >= 2, f"Expected >= 2 SCHEMA_* codes, got: {schema_codes}"

    def test_canonical_registry_has_infra_codes(self) -> None:
        codes = list_codes(registry_path=CANONICAL_REGISTRY_PATH)
        infra_codes = [c for c in codes if c.startswith("INFRA_")]
        assert len(infra_codes) >= 3, f"Expected >= 3 INFRA_* codes, got: {infra_codes}"

    def test_canonical_registry_has_vm_codes(self) -> None:
        codes = list_codes(registry_path=CANONICAL_REGISTRY_PATH)
        vm_codes = [c for c in codes if c.startswith("VM_")]
        assert len(vm_codes) >= 3, f"Expected >= 3 VM_* codes, got: {vm_codes}"

    def test_canonical_registry_has_network_codes(self) -> None:
        codes = list_codes(registry_path=CANONICAL_REGISTRY_PATH)
        network_codes = [c for c in codes if c.startswith("NETWORK_")]
        assert len(network_codes) >= 3, f"Expected >= 3 NETWORK_* codes, got: {network_codes}"

    def test_canonical_registry_has_gate_codes(self) -> None:
        codes = list_codes(registry_path=CANONICAL_REGISTRY_PATH)
        gate_codes = [c for c in codes if c.startswith("GATE_")]
        assert len(gate_codes) >= 4, f"Expected >= 4 GATE_* codes, got: {gate_codes}"

    def test_canonical_registry_has_exec_codes(self) -> None:
        codes = list_codes(registry_path=CANONICAL_REGISTRY_PATH)
        exec_codes = [c for c in codes if c.startswith("EXEC_")]
        assert len(exec_codes) >= 3, f"Expected >= 3 EXEC_* codes, got: {exec_codes}"

    def test_canonical_registry_has_input_codes(self) -> None:
        codes = list_codes(registry_path=CANONICAL_REGISTRY_PATH)
        input_codes = [c for c in codes if c.startswith("INPUT_")]
        assert len(input_codes) >= 4, f"Expected >= 4 INPUT_* codes, got: {input_codes}"

    def test_all_codes_have_required_fields(self) -> None:
        registry = load_registry(CANONICAL_REGISTRY_PATH)
        fragment = registry.openapi_fragment()
        for code, meta in fragment.items():
            assert "severity" in meta, f"{code}: missing severity"
            assert "category" in meta, f"{code}: missing category"
            assert "retry_advice" in meta, f"{code}: missing retry_advice"
            assert "description" in meta, f"{code}: missing description"

    def test_all_retry_advice_values_are_valid(self) -> None:
        from error_registry import VALID_RETRY_ADVICE

        registry = load_registry(CANONICAL_REGISTRY_PATH)
        fragment = registry.openapi_fragment()
        for code, meta in fragment.items():
            assert meta["retry_advice"] in VALID_RETRY_ADVICE, f"{code}: invalid retry_advice {meta['retry_advice']!r}"

    def test_all_severity_values_are_valid(self) -> None:
        from error_registry import VALID_SEVERITIES

        registry = load_registry(CANONICAL_REGISTRY_PATH)
        fragment = registry.openapi_fragment()
        for code, meta in fragment.items():
            assert meta["severity"] in VALID_SEVERITIES, f"{code}: invalid severity {meta['severity']!r}"

    def test_backoff_codes_with_retry_after_have_non_negative_value(self) -> None:
        registry = load_registry(CANONICAL_REGISTRY_PATH)
        fragment = registry.openapi_fragment()
        for code, meta in fragment.items():
            if meta["retry_advice"] == "backoff" and meta.get("retry_after_s") is not None:
                assert meta["retry_after_s"] >= 0, f"{code}: retry_after_s must be >= 0, got {meta['retry_after_s']}"

    def test_codes_by_category_covers_expected_categories(self) -> None:
        grouped = codes_by_category(registry_path=CANONICAL_REGISTRY_PATH)
        expected_categories = {
            "authentication",
            "authorization",
            "input",
            "infrastructure",
            "platform_gate",
            "execution",
            "health",
            "deployment",
            "configuration",
            "vm",
            "network",
        }
        missing = expected_categories - set(grouped.keys())
        assert not missing, f"Missing categories in registry: {missing}"

    def test_lookup_known_code(self) -> None:
        defn = lookup("AUTH_TOKEN_MISSING", registry_path=CANONICAL_REGISTRY_PATH)
        assert defn.code == "AUTH_TOKEN_MISSING"
        assert defn.http_status == 401
        assert defn.severity == "warn"
        assert defn.retry_advice == "none"

    def test_lookup_unknown_code_raises(self) -> None:
        with pytest.raises(UnknownErrorCode) as exc_info:
            lookup("TOTALLY_FAKE_CODE", registry_path=CANONICAL_REGISTRY_PATH)
        assert "TOTALLY_FAKE_CODE" in str(exc_info.value)

    def test_list_codes_returns_sorted_list(self) -> None:
        codes = list_codes(registry_path=CANONICAL_REGISTRY_PATH)
        assert codes == sorted(codes)
        assert len(codes) > 10


# ---------------------------------------------------------------------------
# validate_registry() — schema enforcement
# ---------------------------------------------------------------------------


class TestValidateRegistry:
    def test_valid_minimal_registry(self) -> None:
        data = yaml.safe_load(minimal_yaml())
        result = validate_registry(data)
        assert "AUTH_TOKEN_MISSING" in result

    def test_rejects_non_dict(self) -> None:
        with pytest.raises(ErrorRegistryError, match="mapping"):
            validate_registry(["not", "a", "dict"])

    def test_rejects_missing_error_codes_key(self) -> None:
        with pytest.raises(ErrorRegistryError, match="error_codes"):
            validate_registry({"schema_version": "1.0.0"})

    def test_rejects_empty_error_codes(self) -> None:
        with pytest.raises(ErrorRegistryError, match="non-empty"):
            validate_registry({"error_codes": {}})

    def test_rejects_non_screaming_snake_code(self) -> None:
        data = {
            "error_codes": {
                "lowercase_code": {
                    "severity": "warn",
                    "category": "auth",
                    "retry_advice": "none",
                    "description": "bad code name",
                }
            }
        }
        with pytest.raises(ErrorRegistryError, match="SCREAMING_SNAKE_CASE"):
            validate_registry(data)

    def test_rejects_single_component_code(self) -> None:
        # Code must have at least two components separated by underscore
        data = {
            "error_codes": {
                "AUTH": {
                    "severity": "warn",
                    "category": "auth",
                    "retry_advice": "none",
                    "description": "too short",
                }
            }
        }
        with pytest.raises(ErrorRegistryError, match="SCREAMING_SNAKE_CASE"):
            validate_registry(data)

    def test_rejects_missing_severity(self) -> None:
        data = {
            "error_codes": {
                "AUTH_MISSING": {
                    "category": "auth",
                    "retry_advice": "none",
                    "description": "no severity",
                }
            }
        }
        with pytest.raises(ErrorRegistryError, match="severity.*missing"):
            validate_registry(data)

    def test_rejects_invalid_severity(self) -> None:
        data = {
            "error_codes": {
                "AUTH_MISSING": {
                    "severity": "verbose",
                    "category": "auth",
                    "retry_advice": "none",
                    "description": "bad severity",
                }
            }
        }
        with pytest.raises(ErrorRegistryError, match="severity"):
            validate_registry(data)

    def test_rejects_invalid_retry_advice(self) -> None:
        data = {
            "error_codes": {
                "AUTH_MISSING": {
                    "severity": "warn",
                    "category": "auth",
                    "retry_advice": "eventually",
                    "description": "bad retry advice",
                }
            }
        }
        with pytest.raises(ErrorRegistryError, match="retry_advice"):
            validate_registry(data)

    def test_rejects_invalid_http_status(self) -> None:
        data = {
            "error_codes": {
                "AUTH_MISSING": {
                    "http_status": 999,
                    "severity": "warn",
                    "category": "auth",
                    "retry_advice": "none",
                    "description": "bad status",
                }
            }
        }
        with pytest.raises(ErrorRegistryError, match="http_status"):
            validate_registry(data)

    def test_rejects_negative_retry_after_s(self) -> None:
        data = {
            "error_codes": {
                "INFRA_LOCK": {
                    "http_status": 503,
                    "severity": "warn",
                    "category": "infra",
                    "retry_advice": "backoff",
                    "retry_after_s": -5,
                    "description": "bad retry_after",
                }
            }
        }
        with pytest.raises(ErrorRegistryError, match="retry_after_s"):
            validate_registry(data)

    def test_accepts_null_retry_after_s(self) -> None:
        data = {
            "error_codes": {
                "GATE_CIRCUIT_OPEN": {
                    "http_status": 503,
                    "severity": "warn",
                    "category": "platform_gate",
                    "retry_advice": "backoff",
                    "retry_after_s": None,
                    "description": "circuit open",
                }
            }
        }
        result = validate_registry(data)
        assert "GATE_CIRCUIT_OPEN" in result

    def test_rejects_invalid_docs_url(self) -> None:
        data = {
            "error_codes": {
                "AUTH_MISSING": {
                    "severity": "warn",
                    "category": "auth",
                    "retry_advice": "none",
                    "description": "bad url",
                    "docs_url": "ftp://not-http.example.com",
                }
            }
        }
        with pytest.raises(ErrorRegistryError, match="docs_url"):
            validate_registry(data)

    def test_rejects_context_fields_non_list(self) -> None:
        data = {
            "error_codes": {
                "AUTH_MISSING": {
                    "severity": "warn",
                    "category": "auth",
                    "retry_advice": "none",
                    "description": "bad context_fields",
                    "context_fields": "not-a-list",
                }
            }
        }
        with pytest.raises(ErrorRegistryError, match="context_fields"):
            validate_registry(data)

    def test_accepts_deprecated_since_field(self) -> None:
        data = {
            "error_codes": {
                "AUTH_OLD": {
                    "severity": "warn",
                    "category": "auth",
                    "retry_advice": "none",
                    "description": "deprecated code",
                    "deprecated_since": "0.150.0",
                }
            }
        }
        result = validate_registry(data)
        assert "AUTH_OLD" in result

    def test_accepts_multiple_valid_codes(self) -> None:
        data = yaml.safe_load(
            textwrap.dedent("""\
            schema_version: 1.0.0
            error_codes:
              AUTH_TOKEN_MISSING:
                http_status: 401
                severity: warn
                category: authentication
                retry_advice: none
                description: Bearer token is required.
                context_fields: [header]
              INFRA_DEPENDENCY_DOWN:
                http_status: 503
                severity: error
                category: infrastructure
                retry_advice: backoff
                retry_after_s: 30
                description: Upstream dependency request failed.
                context_fields: [dependency, detail]
        """)
        )
        result = validate_registry(data)
        assert "AUTH_TOKEN_MISSING" in result
        assert "INFRA_DEPENDENCY_DOWN" in result


# ---------------------------------------------------------------------------
# load_registry() — error paths
# ---------------------------------------------------------------------------


class TestLoadRegistry:
    def test_loads_valid_file(self, tmp_path: Path) -> None:
        path = make_registry(tmp_path, minimal_yaml())
        registry = load_registry(path)
        assert registry is not None

    def test_raises_file_not_found_for_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.yaml"
        with pytest.raises(FileNotFoundError, match="error code registry not found"):
            load_registry(missing)

    def test_raises_error_for_invalid_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "error-codes.yaml"
        path.write_text("{{{{invalid yaml: [}", encoding="utf-8")
        with pytest.raises(ErrorRegistryError, match="not valid YAML"):
            load_registry(path)

    def test_raises_error_for_schema_violation(self, tmp_path: Path) -> None:
        path = tmp_path / "error-codes.yaml"
        path.write_text("error_codes:\n  invalid_code:\n    severity: bad\n", encoding="utf-8")
        with pytest.raises(ErrorRegistryError):
            load_registry(path)

    def test_default_path_resolves_to_canonical_registry(self) -> None:
        # Calling without a path argument should resolve to the canonical file.
        registry = load_registry()
        assert registry is not None
        defn = registry.definition("AUTH_TOKEN_MISSING")
        assert defn.code == "AUTH_TOKEN_MISSING"


# ---------------------------------------------------------------------------
# ErrorRegistry.create() — envelope construction
# ---------------------------------------------------------------------------


class TestErrorRegistryCreate:
    def _make_registry(self, tmp_path: Path) -> ErrorRegistry:
        yaml_content = textwrap.dedent("""\
            schema_version: 1.0.0
            error_codes:
              AUTH_TOKEN_MISSING:
                http_status: 401
                severity: warn
                category: authentication
                retry_advice: none
                description: Bearer token is required.
                context_fields: [header]
              GATE_CIRCUIT_OPEN:
                http_status: 503
                severity: warn
                category: platform_gate
                retry_advice: backoff
                retry_after_s: null
                description: Circuit breaker is open.
                context_fields: [circuit_name, opened_at, recovery_window_s]
              EXEC_WORKFLOW_FAILED:
                http_status: 500
                severity: error
                category: execution
                retry_advice: manual
                description: Workflow failed with non-zero exit status.
                context_fields: [workflow_id, exit_code]
        """)
        path = tmp_path / "error-codes.yaml"
        path.write_text(yaml_content, encoding="utf-8")
        return load_registry(path)

    def test_create_uses_registry_defaults(self, tmp_path: Path) -> None:
        registry = self._make_registry(tmp_path)
        error = registry.create(
            "AUTH_TOKEN_MISSING",
            trace_id="t-001",
        )
        assert isinstance(error, CanonicalError)
        assert error.code == "AUTH_TOKEN_MISSING"
        assert error.http_status == 401
        assert error.retry_advice == "none"
        assert error.trace_id == "t-001"

    def test_create_allows_message_override(self, tmp_path: Path) -> None:
        registry = self._make_registry(tmp_path)
        error = registry.create(
            "AUTH_TOKEN_MISSING",
            trace_id="t-002",
            message="Custom error message for this request.",
        )
        assert error.message == "Custom error message for this request."

    def test_create_filters_context_to_declared_fields(self, tmp_path: Path) -> None:
        registry = self._make_registry(tmp_path)
        error = registry.create(
            "GATE_CIRCUIT_OPEN",
            trace_id="t-003",
            context={
                "circuit_name": "postgres",
                "opened_at": "2026-04-08T00:00:00Z",
                "recovery_window_s": 120,
                "extra_field": "should be ignored",
            },
        )
        assert error.context == {
            "circuit_name": "postgres",
            "opened_at": "2026-04-08T00:00:00Z",
            "recovery_window_s": 120,
        }
        assert "extra_field" not in error.context

    def test_create_allows_retry_after_s_override(self, tmp_path: Path) -> None:
        registry = self._make_registry(tmp_path)
        error = registry.create(
            "GATE_CIRCUIT_OPEN",
            trace_id="t-004",
            retry_after_s=300,
        )
        assert error.retry_after_s == 300

    def test_create_raises_for_unknown_code(self, tmp_path: Path) -> None:
        registry = self._make_registry(tmp_path)
        with pytest.raises(KeyError, match="unknown error code"):
            registry.create("DOES_NOT_EXIST", trace_id="t-999")


# ---------------------------------------------------------------------------
# CanonicalError.to_response() — envelope shape
# ---------------------------------------------------------------------------


class TestCanonicalErrorToResponse:
    def _make_error(self, **kwargs) -> CanonicalError:
        defaults = dict(
            code="AUTH_TOKEN_MISSING",
            message="No bearer token provided.",
            trace_id="trace-abc",
            http_status=401,
            retry_advice="none",
        )
        defaults.update(kwargs)
        return CanonicalError(**defaults)

    def test_envelope_has_error_key(self) -> None:
        response = self._make_error().to_response()
        assert "error" in response

    def test_envelope_contains_required_fields(self) -> None:
        response = self._make_error().to_response()
        error = response["error"]
        for field in ("code", "message", "trace_id", "retry_advice", "occurred_at"):
            assert field in error, f"missing field: {field}"

    def test_envelope_code_matches(self) -> None:
        response = self._make_error(code="EXEC_WORKFLOW_FAILED", http_status=500).to_response()
        assert response["error"]["code"] == "EXEC_WORKFLOW_FAILED"

    def test_envelope_trace_id_preserved(self) -> None:
        response = self._make_error(trace_id="my-trace-xyz").to_response()
        assert response["error"]["trace_id"] == "my-trace-xyz"

    def test_envelope_context_included_when_set(self) -> None:
        error = self._make_error()
        error.context = {"reason": "expired"}
        response = error.to_response()
        assert response["error"]["context"] == {"reason": "expired"}

    def test_envelope_context_absent_when_empty(self) -> None:
        error = self._make_error()
        error.context = {}
        response = error.to_response()
        assert "context" not in response["error"]

    def test_envelope_retry_after_included(self) -> None:
        error = self._make_error(
            code="GATE_CIRCUIT_OPEN",
            http_status=503,
            retry_advice="backoff",
            retry_after_s=120,
        )
        response = error.to_response()
        assert response["error"]["retry_after"] == 120

    def test_envelope_docs_url_included_when_set(self) -> None:
        error = self._make_error(docs_url="https://docs.example.com/adr/0056")
        response = error.to_response()
        assert response["error"]["docs_url"] == "https://docs.example.com/adr/0056"


# ---------------------------------------------------------------------------
# list_codes() and codes_by_category()
# ---------------------------------------------------------------------------


class TestConvenienceFunctions:
    def test_list_codes_is_sorted(self, tmp_path: Path) -> None:
        path = tmp_path / "error-codes.yaml"
        path.write_text(
            textwrap.dedent("""\
            schema_version: 1.0.0
            error_codes:
              AUTH_TOKEN_MISSING:
                http_status: 401
                severity: warn
                category: authentication
                retry_advice: none
                description: Bearer token is required.
                context_fields: [header]
              INFRA_DOWN:
                http_status: 503
                severity: error
                category: infrastructure
                retry_advice: backoff
                description: Service down.
        """),
            encoding="utf-8",
        )
        codes = list_codes(registry_path=path)
        assert codes == sorted(codes)
        assert "AUTH_TOKEN_MISSING" in codes
        assert "INFRA_DOWN" in codes

    def test_codes_by_category_groups_correctly(self, tmp_path: Path) -> None:
        path = tmp_path / "error-codes.yaml"
        path.write_text(
            textwrap.dedent("""\
            schema_version: 1.0.0
            error_codes:
              AUTH_TOKEN_MISSING:
                http_status: 401
                severity: warn
                category: authentication
                retry_advice: none
                description: Bearer token is required.
                context_fields: [header]
              INFRA_DOWN:
                http_status: 503
                severity: error
                category: infrastructure
                retry_advice: backoff
                description: Service down.
              INFRA_LOCK:
                http_status: 503
                severity: warn
                category: infrastructure
                retry_advice: backoff
                description: Lock held.
        """),
            encoding="utf-8",
        )
        grouped = codes_by_category(registry_path=path)
        assert "authentication" in grouped
        assert "infrastructure" in grouped
        assert grouped["authentication"] == sorted(grouped["authentication"])
        assert "INFRA_DOWN" in grouped["infrastructure"]
        assert "INFRA_LOCK" in grouped["infrastructure"]

    def test_codes_by_category_lists_within_each_category_are_sorted(self) -> None:
        grouped = codes_by_category(registry_path=CANONICAL_REGISTRY_PATH)
        for category, codes in grouped.items():
            assert codes == sorted(codes), f"category {category!r} is not sorted"


# ---------------------------------------------------------------------------
# UnknownErrorCode exception
# ---------------------------------------------------------------------------


class TestUnknownErrorCode:
    def test_is_key_error_subclass(self) -> None:
        exc = UnknownErrorCode("MY_CODE")
        assert isinstance(exc, KeyError)

    def test_carries_code_attribute(self) -> None:
        exc = UnknownErrorCode("MY_CODE")
        assert exc.code == "MY_CODE"

    def test_message_contains_code(self) -> None:
        exc = UnknownErrorCode("MY_CODE")
        assert "MY_CODE" in str(exc)
