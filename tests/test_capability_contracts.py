from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "capability_contracts.py"


def load_module(name: str):
    scripts_dir = REPO_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_repo_catalog_validates() -> None:
    module = load_module("capability_contracts_repo")
    catalog = module.load_capability_contract_catalog()

    module.validate_capability_contract_catalog(catalog)

    summary = module.summarize_capability_contracts(catalog)
    assert summary["summary"]["total"] >= 6
    assert summary["summary"]["selected"] >= 6


def test_validate_rejects_unknown_service_id(tmp_path: Path) -> None:
    module = load_module("capability_contracts_invalid")
    module.CAPABILITY_CONTRACT_SCHEMA_PATH = REPO_ROOT / "docs" / "schema" / "capability-contract-catalog.schema.json"
    module.ADR_DIR = tmp_path / "docs" / "adr"
    write(
        module.ADR_DIR / "0056-keycloak.md",
        "# ADR 0056\n",
    )
    write(
        tmp_path / "docs" / "runbooks" / "configure-keycloak.md",
        "# Configure Keycloak\n",
    )
    service_catalog = {
        "services": [
            {
                "id": "windmill",
                "name": "Windmill"
            }
        ]
    }
    catalog = {
        "$schema": "docs/schema/capability-contract-catalog.schema.json",
        "schema_version": "1.0.0",
        "capabilities": [
            {
                "id": "identity_provider",
                "name": "Identity Provider",
                "summary": "Test contract.",
                "scope": "critical_shared_surface",
                "owner": "platform",
                "review_cadence": "quarterly",
                "required_outcomes": ["Authenticate."],
                "service_guarantees": ["Stable OIDC endpoints."],
                "canonical_inputs": [{"name": "login", "description": "Login request."}],
                "canonical_outputs": [{"name": "token", "description": "Identity token."}],
                "security_expectations": ["MFA."],
                "audit_expectations": ["Audit logs."],
                "observability_requirements": ["Health check."],
                "portability_constraints": ["Portable OIDC contract."],
                "migration_expectations": {
                    "export_formats": ["realm export"],
                    "import_requirements": ["Replacement can import clients."],
                    "fallback_behaviour": "New logins fail closed."
                },
                "failure_modes": [
                    {
                        "mode": "provider unavailable",
                        "acceptable_degradation": "Existing sessions continue briefly.",
                        "operator_response": "Use break-glass identities."
                    }
                ],
                "current_selection": {
                    "product_name": "Keycloak",
                    "service_id": "keycloak",
                    "selection_adr": "0056",
                    "runbook": "docs/runbooks/configure-keycloak.md",
                    "notes": "Selected for OIDC."
                }
            }
        ]
    }

    with pytest.raises(ValueError, match="unknown service 'keycloak'"):
        module.validate_capability_contract_catalog(catalog, service_catalog=service_catalog, catalog_path=tmp_path / "catalog.json")
